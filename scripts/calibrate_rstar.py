#!/usr/bin/env python3
"""Scripts: Calibrate R* thresholds from the validated harness.

Derives the calibrated thresholds ``(Mmin, epsilon, tau_max, sigma)`` for the
R* profile by exercising the *production* verification harness (the same CLI
handlers a verifier runs) over several seeds on the in-process plant:

* ``Mmin`` is the one-sided 95% lower bound (5th percentile) of the baseline
  ``M (dB)`` distribution, floored at 1 dB.
* ``epsilon`` is the 90th percentile of the SC1 dip ``delta`` over the
  power-sag battery plus a small safety margin, capped at 0.5 (a cap that
  only rejects near-total collapse).
* ``tau_max`` is the 95th percentile of the measured recovery time
  ``tau_rec`` plus a ``max(3*dt, 5 s)`` cushion.
* ``sigma`` is the additive ``L`` margin consistent with ``Mmin`` and the
  typical baseline ``L_ex`` (``sigma = (10**(Mmin/10) - 1) * L_ex``). Under
  the engaged loop ``L_ex`` falls below the ``L`` noise floor, so ``sigma`` is
  evaluated at that floor (the raw ``L_ex`` is recorded for transparency).

It writes ``configs/profile_rstar.yml`` and emits an R0-vs-R* comparison
(CSV + figure) plus a JSON summary for the paper supplement. Because it reuses
the validated profile (``configs/profile_r0.yml``) for ``dt``, the window
length, the estimator, ``p_lag``, and ``n_boot``, the calibrated thresholds are
directly compatible with what the harness produces at run time.

Run:

    python scripts/calibrate_rstar.py --baseline-seeds 6 --sag-seeds 6

See Also:
    paper/main.tex: Methods: Threshold Calibration.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Mapping

import numpy as np
import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import study  # noqa: E402  (local scripts module)


# --------------------------------------------------------------------------- #
# Baseline M and typical L_ex
# --------------------------------------------------------------------------- #
def _pool_window_M(run_dir: str) -> List[float]:
    """Return all per-window ``M (dB)`` values from a run's audit log."""
    ms: List[float] = []
    audit_path = os.path.join(run_dir, "audits", "audit.jsonl")
    if not os.path.exists(audit_path):
        return ms
    with open(audit_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            e = json.loads(line)
            if e.get("event") == "window_measured":
                m = e.get("details", {}).get("M")
                if m is not None:
                    ms.append(float(m))
    return ms


def measure_typical_L_ex(prof: Dict[str, Any], steps: int = 240) -> float:
    """Measure a representative baseline ``L_ex`` with the engaged loop.

    Mirrors the production baseline measurement (controller + estimator on the
    in-process plant) just long enough to obtain a stable median ``L_ex``,
    which is needed to express ``Mmin`` as an additive ``sigma`` margin. This
    is the only quantity calibration needs that the harness deliberately does
    not export, so it is recomputed here directly.

    Args:
        prof: Loaded R0 profile (for dt/window/method/p_lag/n_boot).
        steps: Number of plant ticks to simulate.

    Returns:
        Median baseline ``L_ex`` over the ready windows.
    """
    from ldtc.arbiter.policy import ControllerPolicy
    from ldtc.arbiter.refusal import RefusalArbiter
    from ldtc.lmeas.estimators import estimate_L
    from ldtc.lmeas.metrics import m_db
    from ldtc.lmeas.partition import PartitionManager
    from ldtc.plant.adapter import PlantAdapter
    from ldtc.plant.models import Action
    from ldtc.runtime.windows import SlidingWindow

    dt = float(prof.get("dt", 0.05))
    window = max(4, int(float(prof.get("window_sec", 3.0)) / dt))
    method = str(prof.get("method", "linear"))
    p_lag = int(prof.get("p_lag", 3))
    mi_lag = int(prof.get("mi_lag", 1))
    n_boot = int(prof.get("n_boot", 32))
    mi_k = int(prof.get("mi_k", 5))
    Mmin = float(prof.get("Mmin_db", 3.0))

    order = ["E", "T", "R", "demand", "io", "H"]
    adapter = PlantAdapter()
    sw = SlidingWindow(capacity=window, channel_order=order)
    pm = PartitionManager(N_signals=len(order), seed_C=[0, 1, 2])
    policy = ControllerPolicy(refusal=RefusalArbiter(Mmin_db=Mmin))

    L_ex_vals: List[float] = []
    predicted = 0.0
    for _ in range(steps):
        st = adapter.read_state()
        act = policy.compute(st, predicted_M_db=predicted, risky_cmd=None)
        adapter.write_actuators(action=Action(**act.__dict__))
        st2 = adapter.read_state()
        sw.append(st2)
        if sw.ready():
            X = np.asarray(sw.get_matrix())
            part = pm.get()
            res = estimate_L(
                X=X,
                C=part.C,
                Ex=part.Ex,
                method=method,
                p=p_lag,
                lag_mi=mi_lag,
                n_boot=max(8, n_boot // 4),
                mi_k=mi_k,
            )
            predicted = m_db(res.L_loop, res.L_ex)
            L_ex_vals.append(float(res.L_ex))
    return float(np.median(L_ex_vals)) if L_ex_vals else 0.0


# --------------------------------------------------------------------------- #
# Comparison artifacts
# --------------------------------------------------------------------------- #
def _load_yaml(path: str) -> Mapping[str, Any]:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        try:
            obj = yaml.safe_load(f) or {}
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}


def write_profile_yaml(out_path: str, base: Dict[str, Any], thr: Dict[str, float], baseline_sec: float) -> None:
    """Write the calibrated R* profile, inheriting R0's measurement knobs."""
    data = {
        "profile_id": 1,
        "dt": float(base.get("dt", 0.05)),
        "window_sec": float(base.get("window_sec", 3.0)),
        "method": str(base.get("method", "linear")),
        "p_lag": int(base.get("p_lag", 3)),
        "mi_lag": int(base.get("mi_lag", 1)),
        "n_boot": int(base.get("n_boot", 32)),
        "mi_k": int(base.get("mi_k", 5)),
        "Mmin_db": float(thr["Mmin_db"]),
        "epsilon": float(thr["epsilon"]),
        "tau_max": float(thr["tau_max"]),
        "sigma": float(thr["sigma"]),
        "baseline_sec": float(baseline_sec),
        "diag_cadence_windows": int(base.get("diag_cadence_windows", 25)),
        "realtime": bool(base.get("realtime", False)),
    }
    with open(out_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False)


def write_compare_csv(out_csv: str, r0: Mapping[str, Any], thr: Dict[str, float]) -> None:
    """Write a CSV comparing R0 parameters with calibrated R*."""
    import csv

    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    rows = [
        ("Mmin_db", r0.get("Mmin_db", float("nan")), thr["Mmin_db"]),
        ("epsilon", r0.get("epsilon", float("nan")), thr["epsilon"]),
        ("tau_max", r0.get("tau_max", float("nan")), thr["tau_max"]),
        ("sigma", float("nan"), thr["sigma"]),
    ]
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["param", "R0", "R*"])
        for name, r0v, rsv in rows:
            try:
                r0f = float(r0v)
            except Exception:
                r0f = float("nan")
            w.writerow([name, f"{r0f:.6g}" if np.isfinite(r0f) else "", f"{rsv:.6g}"])


def write_compare_figure(out_png: str, r0: Mapping[str, Any], thr: Dict[str, float]) -> None:
    """Write a grouped bar chart comparing R0 vs R* thresholds."""
    import matplotlib.pyplot as plt

    from ldtc.reporting.style import COLORS, apply_matplotlib_theme

    os.makedirs(os.path.dirname(out_png), exist_ok=True)
    params = ["Mmin_db", "epsilon", "tau_max", "sigma"]
    r0_vals = [float(r0.get(k, np.nan)) if r0.get(k) is not None else np.nan for k in params]
    rstar_vals = [thr[k] for k in params]
    x = np.arange(len(params))
    width = 0.38
    apply_matplotlib_theme("paper")
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    r0_plot = [v if np.isfinite(v) else 0.0 for v in r0_vals]
    ax.bar(x - width / 2, r0_plot, width=width, label="R0", color=COLORS["blue_light"])
    ax.bar(x + width / 2, rstar_vals, width=width, label="R*", color=COLORS["blue"])
    for xi, (a, b) in enumerate(zip(r0_vals, rstar_vals)):
        if np.isfinite(a):
            ax.text(xi - width / 2, a, f"{a:.2g}", ha="center", va="bottom", fontsize=8)
        ax.text(xi + width / 2, b, f"{b:.2g}", ha="center", va="bottom", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(params)
    ax.set_ylabel("Value")
    ax.set_title("R0 (generic) vs R* (calibrated) thresholds")
    ax.legend(frameon=False)
    fig.tight_layout()
    for ext in ("png", "pdf", "svg"):
        fig.savefig(os.path.splitext(out_png)[0] + "." + ext, dpi=300, bbox_inches="tight")
    plt.close(fig)


# --------------------------------------------------------------------------- #
# Calibration
# --------------------------------------------------------------------------- #
def calibrate(args: argparse.Namespace) -> Dict[str, Any]:
    """Run the calibration battery and return the threshold dict + provenance."""
    os.environ["LDTC_SKIP_REPORT"] = "1"
    base_cfg = dict(_load_yaml(os.path.join(REPO_ROOT, "configs", "profile_r0.yml")))
    dt = float(base_cfg.get("dt", 0.05))

    scen = {s.name: s for s in study.default_scenarios()}
    pos = scen["positive"]
    sag = scen["sc1_power_sag"]

    import tempfile

    pooled_M: List[float] = []
    deltas: List[float] = []
    taus: List[float] = []
    with tempfile.TemporaryDirectory(prefix="ldtc_calib_") as tmp:
        print(f"Baseline battery: {args.baseline_seeds} seeds")
        for i in range(int(args.baseline_seeds)):
            seed = int(args.seed_base) + i
            rm = study.run_one(pos, seed, tmp)
            if rm is None or not rm.valid:
                print(f"  baseline seed={seed}: skipped (invalid run)")
                continue
            ms = _pool_window_M(rm.run_dir)
            pooled_M.extend(ms)
            print(f"  baseline seed={seed}: {len(ms)} windows, median M={rm.M_median:+.1f} dB")

        print(f"Power-sag battery: {args.sag_seeds} seeds")
        for i in range(int(args.sag_seeds)):
            seed = int(args.seed_base) + 100 + i
            rm = study.run_one(sag, seed, tmp)
            if rm is None or not rm.valid:
                print(f"  power-sag seed={seed}: skipped (invalid run)")
                continue
            if rm.sc1_delta is not None:
                deltas.append(rm.sc1_delta)
            if rm.sc1_tau_rec is not None:
                taus.append(rm.sc1_tau_rec)
            print(f"  power-sag seed={seed}: delta={rm.sc1_delta}, tau_rec={rm.sc1_tau_rec}s")

    if not pooled_M:
        raise RuntimeError("Baseline battery produced no valid M samples")
    M_arr = np.asarray([m for m in pooled_M if np.isfinite(m)], dtype=float)
    Mmin_db = max(1.0, float(np.percentile(M_arr, 5.0)))

    # epsilon is the 90th percentile of the observed fractional L_loop dip plus a
    # small margin. The cap (0.5) only rejects pathological near-total collapse:
    # a 0.5 fractional L_loop drop is just ~3 dB of M, so the engaged loop is
    # still overwhelmingly dominant; values in this range are genuinely resilient.
    if deltas:
        eps_star = min(0.50, max(0.10, float(np.percentile(np.asarray(deltas), 90.0)) + float(args.safety_margin)))
    else:
        eps_star = 0.15
    if taus:
        tau_star = float(np.percentile(np.asarray(taus), 95.0)) + max(3.0 * dt, 5.0)
    else:
        tau_star = 60.0

    print("Measuring typical baseline L_ex for sigma...")
    # Under the engaged loop the controller drives exchange predictability below
    # the L noise floor, so the raw median L_ex is ~0 (a strong NC1 signal). sigma
    # is the additive-margin restatement of Mmin, so we evaluate it at the same
    # floor m_db uses; we also record the raw value for transparency.
    L_ex_floor = 1e-3  # matches the m_db() noise floor
    L_ex_raw = measure_typical_L_ex(base_cfg)
    L_ex_eff = max(L_ex_floor, L_ex_raw)
    ratio = 10.0 ** (Mmin_db / 10.0)
    sigma = max(0.0, (ratio - 1.0) * L_ex_eff)

    thr = {"Mmin_db": Mmin_db, "epsilon": eps_star, "tau_max": tau_star, "sigma": sigma}
    provenance = {
        "n_baseline_windows": int(M_arr.size),
        "baseline_M_p5": float(np.percentile(M_arr, 5.0)),
        "baseline_M_median": float(np.median(M_arr)),
        "n_sag_trials": len(deltas),
        "delta_p90": (float(np.percentile(np.asarray(deltas), 90.0)) if deltas else None),
        "tau_p95": (float(np.percentile(np.asarray(taus), 95.0)) if taus else None),
        "L_ex_raw_median": L_ex_raw,
        "L_ex_floor": L_ex_floor,
        "L_ex_effective": L_ex_eff,
        "base_profile": "configs/profile_r0.yml",
    }
    return {"thresholds": thr, "provenance": provenance, "base_cfg": base_cfg}


def main() -> None:
    """CLI entry point for R* calibration."""
    ap = argparse.ArgumentParser(
        description="Calibrate R* thresholds from the validated harness and write configs/profile_rstar.yml"
    )
    ap.add_argument("--baseline-seeds", type=int, default=6)
    ap.add_argument("--sag-seeds", type=int, default=6)
    ap.add_argument("--seed-base", type=int, default=40000)
    ap.add_argument("--safety-margin", type=float, default=0.02)
    cal_dir = os.path.join(REPO_ROOT, "artifacts", "calibration")
    ap.add_argument("--out", type=str, default=os.path.join(REPO_ROOT, "configs", "profile_rstar.yml"))
    ap.add_argument("--summary", type=str, default=os.path.join(cal_dir, "rstar_summary.json"))
    ap.add_argument("--compare-csv", type=str, default=os.path.join(cal_dir, "r0_vs_rstar.csv"))
    ap.add_argument("--compare-fig", type=str, default=os.path.join(cal_dir, "r0_vs_rstar.png"))
    ap.add_argument("--lock-profile", action="store_true", default=False, help="chmod 444 the written profile")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    os.makedirs(os.path.dirname(args.summary), exist_ok=True)

    result = calibrate(args)
    thr = result["thresholds"]
    base_cfg = result["base_cfg"]
    baseline_sec = float(base_cfg.get("baseline_sec", 18.0))

    write_profile_yaml(args.out, base_cfg, thr, baseline_sec)
    if args.lock_profile:
        try:
            os.chmod(args.out, 0o444)
        except Exception:
            pass

    r0_loaded = _load_yaml(os.path.join(REPO_ROOT, "configs", "profile_r0.yml"))
    write_compare_csv(args.compare_csv, r0_loaded, thr)
    write_compare_figure(args.compare_fig, r0_loaded, thr)

    summary = {
        "thresholds": thr,
        "provenance": result["provenance"],
        "timestamp": time.time(),
        "note": "R* thresholds calibrated on the in-process plant via the production harness (R0 measurement knobs).",
        "artifacts": {
            "profile": os.path.abspath(args.out),
            "compare_csv": os.path.abspath(args.compare_csv),
            "compare_fig": os.path.abspath(os.path.splitext(args.compare_fig)[0] + ".png"),
        },
    }
    with open(args.summary, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n=== R* calibration ===")
    print(f"  Mmin_db = {thr['Mmin_db']:.2f}  (R0: {r0_loaded.get('Mmin_db')})")
    print(f"  epsilon = {thr['epsilon']:.3f}  (R0: {r0_loaded.get('epsilon')})")
    print(f"  tau_max = {thr['tau_max']:.2f}  (R0: {r0_loaded.get('tau_max')})")
    print(f"  sigma   = {thr['sigma']:.4f}")
    print(f"Wrote calibrated profile: {args.out}")
    print(f"Wrote summary: {args.summary}")


if __name__ == "__main__":
    main()
