#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import json
import time
import argparse
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple, Mapping

import numpy as np
import yaml
import matplotlib.pyplot as plt
from ldtc.reporting.style import apply_matplotlib_theme, COLORS

from ldtc.runtime.windows import SlidingWindow
from ldtc.lmeas.partition import PartitionManager
from ldtc.lmeas.estimators import estimate_L
from ldtc.lmeas.metrics import m_db
from ldtc.plant.adapter import PlantAdapter
from ldtc.plant.models import Action

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@dataclass
class CalibInputs:
    dt: float
    window_sec: float
    method: str
    p_lag: int
    mi_lag: int
    n_boot: int
    baseline_sec: float
    omega_trials: int
    sag_drop: float
    sag_duration: float
    safety_margin: float


@dataclass
class CalibOutputs:
    Mmin_db: float
    epsilon: float
    tau_max: float
    sigma: float
    profile_id: int


def _print_progress(prefix: str, i: int, total: int) -> None:
    i = max(0, min(i, total))
    pct = int(100 * i / max(1, total))
    bar_len = 20
    filled = int(bar_len * pct / 100)
    bar = "#" * filled + "-" * (bar_len - filled)
    sys.stdout.write(f"\r{prefix} [{bar}] {pct}% ({i}/{total})")
    sys.stdout.flush()
    if i == total:
        sys.stdout.write("\n")


def run_baseline_once(inp: CalibInputs, seed_C: List[int]) -> Dict[str, List[float]]:
    window = max(4, int(inp.window_sec / inp.dt))
    adapter = PlantAdapter()
    order = ["E", "T", "R", "demand", "io", "H"]
    sw = SlidingWindow(capacity=window, channel_order=order)
    pm = PartitionManager(N_signals=len(order), seed_C=seed_C)

    M_series: List[float] = []
    L_ex_series: List[float] = []

    steps = max(1, int(inp.baseline_sec / inp.dt))
    for step in range(steps):
        adapter.read_state()
        adapter.write_actuators(action=Action())
        st = adapter.read_state()
        sw.append(st)
        if sw.ready():
            X = np.asarray(sw.get_matrix())
            part = pm.get()
            res = estimate_L(
                X=X,
                C=part.C,
                Ex=part.Ex,
                method=inp.method,
                p=inp.p_lag,
                lag_mi=inp.mi_lag,
                n_boot=max(8, inp.n_boot // 2),
            )
            M_series.append(m_db(res.L_loop, res.L_ex))
            # Record L_ex for sigma estimate
            L_ex_series.append(float(res.L_ex))
        if (step % max(1, steps // 50)) == 0:
            _print_progress("Baseline", step, steps)
    _print_progress("Baseline", steps, steps)
    return {"M": M_series, "L_ex": L_ex_series}


def run_power_sag_once(inp: CalibInputs, seed_C: List[int]) -> Tuple[float, float]:
    """
    Returns (delta, tau_rec_sec) for a single Ω power-sag trial.
    """
    window = max(4, int(inp.window_sec / inp.dt))
    adapter = PlantAdapter()
    order = ["E", "T", "R", "demand", "io", "H"]
    sw = SlidingWindow(capacity=window, channel_order=order)
    pm = PartitionManager(N_signals=len(order), seed_C=seed_C)

    # Baseline settle 2 s
    L_loop_baseline = None
    L_loop_trough = None
    recovery_start_idx = None
    omega_onset_idx = None
    sustained_ok = 0
    sustained_required = 2
    Mmin_for_detect = 0.0  # use 0 dB provisional for recovery detect here
    last_idx_written = 0

    def step_once() -> Tuple[float, float, float]:
        nonlocal last_idx_written
        adapter.read_state()
        adapter.write_actuators(action=Action())
        st = adapter.read_state()
        sw.append(st)
        if sw.ready():
            X = np.asarray(sw.get_matrix())
            part = pm.get()
            res = estimate_L(
                X=X,
                C=part.C,
                Ex=part.Ex,
                method=inp.method,
                p=inp.p_lag,
                lag_mi=inp.mi_lag,
                n_boot=max(8, inp.n_boot // 2),
            )
            last_idx_written += 1
            return float(res.L_loop), float(res.L_ex), m_db(res.L_loop, res.L_ex)
        return (np.nan, np.nan, np.nan)

    # baseline phase (simulate without real-time sleep)
    settle_steps = max(1, int(2.0 / inp.dt))
    for step in range(settle_steps):
        L_loop, L_ex, M = step_once()
        if not np.isnan(L_loop):
            L_loop_baseline = (
                L_loop
                if L_loop_baseline is None
                else 0.9 * L_loop_baseline + 0.1 * L_loop
            )
        if (step % max(1, settle_steps // 20)) == 0:
            _print_progress("Ω trial settle", step, settle_steps)
    _print_progress("Ω trial settle", settle_steps, settle_steps)

    # apply sag
    pm.freeze(True)
    omega_onset_idx = last_idx_written
    adapter.apply_omega("power_sag", drop=inp.sag_drop)
    sag_steps = max(1, int(inp.sag_duration / inp.dt))
    for step in range(sag_steps):
        L_loop, L_ex, M = step_once()
        if not np.isnan(L_loop):
            L_loop_trough = (
                L_loop
                if (L_loop_trough is None or L_loop < L_loop_trough)
                else L_loop_trough
            )
        if (step % max(1, sag_steps // 20)) == 0:
            _print_progress("Ω trial sag", step, sag_steps)
    _print_progress("Ω trial sag", sag_steps, sag_steps)

    # recovery observation
    pm.freeze(False)
    rec_steps = max(1, int(5.0 / inp.dt))
    for step in range(rec_steps):
        L_loop, L_ex, M = step_once()
        if not np.isnan(M):
            if (M >= Mmin_for_detect) and (L_loop >= L_ex):
                sustained_ok += 1
                if sustained_ok == 1 and recovery_start_idx is None:
                    recovery_start_idx = last_idx_written
                if sustained_ok >= sustained_required:
                    break
            else:
                sustained_ok = 0
        if (step % max(1, rec_steps // 20)) == 0:
            _print_progress("Ω trial recovery", step, rec_steps)
    _print_progress("Ω trial recovery", rec_steps, rec_steps)

    if (
        (L_loop_baseline is None)
        or (L_loop_trough is None)
        or (omega_onset_idx is None)
        or (recovery_start_idx is None)
    ):
        return (float("nan"), float("inf"))
    delta = max(0.0, (L_loop_baseline - L_loop_trough) / max(1e-9, L_loop_baseline))
    windows_elapsed = max(0, int(recovery_start_idx - omega_onset_idx))
    tau_rec = windows_elapsed * inp.dt
    return (float(delta), float(tau_rec))


def calibrate_R_star(inp: CalibInputs, seed_C: List[int]) -> CalibOutputs:
    # Baseline: estimate M lower bound and typical L_ex for sigma
    base = run_baseline_once(inp, seed_C=seed_C)
    M_arr = np.asarray(base["M"], dtype=float)
    L_ex_arr = np.asarray(base["L_ex"], dtype=float)
    if M_arr.size == 0 or np.all(~np.isfinite(M_arr)):
        raise RuntimeError("Baseline produced no valid M samples")
    M_arr = M_arr[np.isfinite(M_arr)]
    # One-sided 95% lower bound ≈ 5th percentile
    lb = float(np.percentile(M_arr, 5.0))
    Mmin_db = max(1.0, lb)

    # Sigma: choose additive margin consistent with Mmin relative to typical L_ex
    L_ex_med = float(np.nanmedian(L_ex_arr)) if L_ex_arr.size else 0.0
    ratio = 10.0 ** (Mmin_db / 10.0)
    sigma = max(0.0, (ratio - 1.0) * L_ex_med)

    # Ω trials for epsilon and tau_max
    deltas: List[float] = []
    taus: List[float] = []
    for k in range(inp.omega_trials):
        print(f"\nΩ trial {k+1}/{inp.omega_trials}")
        d, tsec = run_power_sag_once(inp, seed_C=seed_C)
        if np.isfinite(d):
            deltas.append(float(d))
        if np.isfinite(tsec):
            taus.append(float(tsec))
    if not deltas:
        # fallback to conservative defaults
        eps_star = 0.15
    else:
        q90 = float(np.percentile(np.asarray(deltas), 90.0))
        eps_star = min(0.25, max(0.10, q90 + inp.safety_margin))
    if not taus:
        tau_star = 60.0
    else:
        t95 = float(np.percentile(np.asarray(taus), 95.0))
        tau_star = t95 + max(3.0 * inp.dt, 5.0)

    return CalibOutputs(
        Mmin_db=Mmin_db, epsilon=eps_star, tau_max=tau_star, sigma=sigma, profile_id=1
    )


def write_profile_yaml(out_path: str, inp: CalibInputs, out: CalibOutputs) -> None:
    data = {
        "profile_id": int(out.profile_id),
        "dt": float(inp.dt),
        "window_sec": float(inp.window_sec),
        "method": str(inp.method),
        "p_lag": int(inp.p_lag),
        "mi_lag": int(inp.mi_lag),
        "n_boot": int(inp.n_boot),
        "Mmin_db": float(out.Mmin_db),
        "epsilon": float(out.epsilon),
        "tau_max": float(out.tau_max),
        "sigma": float(out.sigma),
        "baseline_sec": float(max(10.0, inp.baseline_sec)),
    }
    with open(out_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False)


def _load_yaml(path: str) -> Mapping[str, Any]:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        try:
            obj = yaml.safe_load(f) or {}
            if not isinstance(obj, dict):
                return {}
            return obj
        except Exception:
            return {}


def _write_compare_csv(out_csv: str, r0: Dict[str, float], rstar: CalibOutputs) -> None:
    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    rows = [
        ("Mmin_db", r0.get("Mmin_db", float("nan")), rstar.Mmin_db),
        ("epsilon", r0.get("epsilon", float("nan")), rstar.epsilon),
        ("tau_max", r0.get("tau_max", float("nan")), rstar.tau_max),
        ("sigma", float("nan"), rstar.sigma),
    ]
    import csv

    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["param", "R0", "R*"])
        for name, r0v, rsv in rows:
            w.writerow([name, f"{r0v:.6g}" if np.isfinite(r0v) else "", f"{rsv:.6g}"])


def _write_compare_figure(
    out_png: str, r0: Dict[str, float], rstar: CalibOutputs
) -> None:
    os.makedirs(os.path.dirname(out_png), exist_ok=True)
    params = ["Mmin_db", "epsilon", "tau_max", "sigma"]
    r0_vals: List[float] = [
        float(r0.get("Mmin_db", np.nan)),
        float(r0.get("epsilon", np.nan)),
        float(r0.get("tau_max", np.nan)),
        np.nan,
    ]
    rstar_vals = [rstar.Mmin_db, rstar.epsilon, rstar.tau_max, rstar.sigma]

    x = np.arange(len(params))
    width = 0.38
    apply_matplotlib_theme("paper")
    plt.figure(figsize=(6.4, 3.2))
    # Plot R0; skip NaNs by replacing with zeros but masking in labels
    r0_plot = [v if np.isfinite(v) else 0.0 for v in r0_vals]
    rstar_plot = rstar_vals
    plt.bar(x - width / 2, r0_plot, width=width, label="R0", color=COLORS["blue_light"])
    plt.bar(x + width / 2, rstar_plot, width=width, label="R*", color=COLORS["blue"])
    plt.xticks(x, params)
    plt.ylabel("Value")
    plt.title("R0 vs R* thresholds")
    plt.legend(frameon=False)
    plt.tight_layout()
    plt.savefig(out_png)
    plt.close()


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Calibrate R* thresholds (Mmin, epsilon, tau_max, sigma) and write configs/profile_rstar.yml"
    )
    ap.add_argument("--dt", type=float, default=0.01)
    ap.add_argument("--window-sec", type=float, default=0.25)
    ap.add_argument("--method", type=str, default="linear", choices=["linear", "mi"])
    ap.add_argument("--p-lag", type=int, default=3)
    ap.add_argument("--mi-lag", type=int, default=1)
    ap.add_argument("--n-boot", type=int, default=32)
    ap.add_argument("--baseline-sec", type=float, default=15.0)
    ap.add_argument("--omega-trials", type=int, default=6)
    ap.add_argument("--sag-drop", type=float, default=0.3)
    ap.add_argument("--sag-duration", type=float, default=8.0)
    ap.add_argument("--safety-margin", type=float, default=0.02)
    ap.add_argument(
        "--out",
        type=str,
        default=os.path.join(REPO_ROOT, "configs", "profile_rstar.yml"),
    )
    ap.add_argument(
        "--summary",
        type=str,
        default=os.path.join(
            REPO_ROOT, "artifacts", "calibration", "rstar_summary.json"
        ),
    )
    ap.add_argument(
        "--compare-csv",
        type=str,
        default=os.path.join(REPO_ROOT, "artifacts", "calibration", "r0_vs_rstar.csv"),
    )
    ap.add_argument(
        "--compare-fig",
        type=str,
        default=os.path.join(REPO_ROOT, "artifacts", "calibration", "r0_vs_rstar.png"),
    )
    ap.add_argument(
        "--lock-profile",
        action="store_true",
        default=True,
        help="Make the written profile read-only (chmod 444)",
    )
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    os.makedirs(os.path.dirname(args.summary), exist_ok=True)

    inp = CalibInputs(
        dt=float(args.dt),
        window_sec=float(args.window_sec),
        method=str(args.method),
        p_lag=int(args.p_lag),
        mi_lag=int(args.mi_lag),
        n_boot=int(args.n_boot),
        baseline_sec=float(args.baseline_sec),
        omega_trials=int(args.omega_trials),
        sag_drop=float(args.sag_drop),
        sag_duration=float(args.sag_duration),
        safety_margin=float(args.safety_margin),
    )

    # Seed C matches the baseline CLI: internal states [E, T, R] -> 0,1,2
    seed_C = [0, 1, 2]

    out = calibrate_R_star(inp, seed_C=seed_C)
    write_profile_yaml(args.out, inp, out)
    # Optionally lock the profile file (read-only)
    if args.lock_profile:
        try:
            os.chmod(args.out, 0o444)
        except Exception:
            pass

    # Compare against R0 and emit CSV/figure
    r0_path = os.path.join(REPO_ROOT, "configs", "profile_r0.yml")
    r0_loaded = _load_yaml(r0_path)
    # Filter numeric fields only to satisfy type expectations
    r0_numeric: Dict[str, float] = {}
    for k, v in r0_loaded.items() if hasattr(r0_loaded, "items") else []:
        try:
            r0_numeric[str(k)] = float(v)
        except Exception:
            continue
    _write_compare_csv(args.compare_csv, r0_numeric, out)
    _write_compare_figure(args.compare_fig, r0_numeric, out)

    summary = {
        "inputs": inp.__dict__,
        "outputs": out.__dict__,
        "timestamp": time.time(),
        "repo_root": REPO_ROOT,
        "note": "R* thresholds calibrated on synthetic baseline + Ω power-sag trials",
        "artifacts": {
            "profile": os.path.abspath(args.out),
            "compare_csv": os.path.abspath(args.compare_csv),
            "compare_fig": os.path.abspath(args.compare_fig),
        },
    }
    with open(args.summary, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"Wrote calibrated profile: {args.out}")
    print(f"Wrote calibration summary: {args.summary}")


if __name__ == "__main__":
    main()
