#!/usr/bin/env python3
"""Scripts: Emergence-under-learning measurement sweep.

Takes the policy checkpoints written by ``scripts/train_agent.py`` (fixed
training fractions of the same run) and measures each one with the
*production* verification harness (the ``run-policy`` CLI handler): same
estimators, same guardrails, same audit chain as every other run in the
paper, across ``N`` seeds per checkpoint. At the final checkpoint it also
measures the two state-independent ablations (``shuffled`` and
``frozen``), which preserve the trained policy's action statistics while
severing the closed loop.

Outputs (under ``--out``): ``emergence_results.json`` and ``.csv`` with
per-condition aggregates and per-run rows, and
``figures/fig_emergence.{png,pdf,svg}`` charting the training curve and
median loop dominance ``M`` against training progress with the ablation
endpoints.

Run (after training):

    python scripts/train_agent.py
    python scripts/emergence.py --seeds 15 --rstar

See Also:
    paper/main.tex: Results (loop dominance emerges under learning).
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
import tempfile
import time
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import study  # noqa: E402  (study utilities: parsing, CIs, run-dir discovery)

RUNS_DIR = study.RUNS_DIR

# Shortened run length for the sweep (same override the study battery uses
# for its NC1 scenarios, so the per-window geometry stays identical).
DEFAULT_OVERRIDES: Dict[str, Any] = {"baseline_sec": 12.0, "diag_cadence_windows": 50}

ABLATIONS: Tuple[str, ...] = ("shuffled", "frozen")


# --------------------------------------------------------------------------- #
# Conditions (checkpoints and ablations)
# --------------------------------------------------------------------------- #
def discover_checkpoints(ckpt_dir: str) -> List[Dict[str, Any]]:
    """Find policy checkpoints and their training fractions.

    Args:
        ckpt_dir: Directory holding ``ckpt_*.json`` files written by
            ``scripts/train_agent.py``.

    Returns:
        List of ``{"path", "frac", "generation"}`` dicts sorted by
        training fraction.

    Raises:
        FileNotFoundError: If no checkpoints are found.
    """
    out: List[Dict[str, Any]] = []
    if os.path.isdir(ckpt_dir):
        for name in sorted(os.listdir(ckpt_dir)):
            if not (name.startswith("ckpt_") and name.endswith(".json")):
                continue
            path = os.path.join(ckpt_dir, name)
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            meta = payload.get("meta", {}) or {}
            frac = float(meta.get("frac", int(name[5:8]) / 100.0))
            out.append({"path": path, "frac": frac, "generation": int(meta.get("generation", -1))})
    if not out:
        raise FileNotFoundError(f"No policy checkpoints under {ckpt_dir} (run scripts/train_agent.py first)")
    return sorted(out, key=lambda d: float(d["frac"]))


def condition_name(frac: float, ablation: str = "none") -> str:
    """Stable condition key for tables and figures."""
    if ablation != "none":
        return f"ablate_{ablation}"
    return f"frac_{int(round(100 * frac)):03d}"


# --------------------------------------------------------------------------- #
# Run orchestration (in-process, production handler)
# --------------------------------------------------------------------------- #
def _apply_rstar(overrides: Dict[str, Any], profile_path: str) -> Dict[str, Any]:
    """Merge calibrated decision thresholds into the run overrides."""
    with open(profile_path, "r", encoding="utf-8") as f:
        prof = dict(yaml.safe_load(f) or {})
    thr = {k: prof[k] for k in ("Mmin_db", "epsilon", "tau_max") if k in prof}
    if not thr:
        raise ValueError(f"{profile_path} has no threshold keys")
    out = dict(overrides)
    out.update(thr)
    return out


def run_one_policy(
    base_cfg: Dict[str, Any],
    overrides: Dict[str, Any],
    ckpt_path: str,
    ablation: str,
    frac: float,
    seed: int,
    tmpdir: str,
    verbose: bool = False,
) -> Optional[study.RunMetrics]:
    """Measure one checkpoint (or ablation) at one seed via ``run-policy``.

    Args:
        base_cfg: Loaded base profile dict.
        overrides: Profile overrides (run length, thresholds).
        ckpt_path: Policy checkpoint path.
        ablation: ``"none"``, ``"shuffled"``, or ``"frozen"``.
        frac: Training fraction (for the scenario label).
        seed: Seed for this replicate.
        tmpdir: Directory for the per-run temporary config.
        verbose: If True, let the handler print to stdout.

    Returns:
        Parsed :class:`study.RunMetrics`, or ``None`` if no run directory
        was found.
    """
    from ldtc.cli import main as cli

    name = condition_name(frac, ablation)
    cfg = dict(base_cfg)
    cfg.update(overrides)
    cfg["seed"] = int(seed)
    cfg["seed_py"] = int(seed)
    cfg["seed_np"] = int(seed)
    cfg_path = os.path.join(tmpdir, f"cfg_{name}_seed_{seed}.yml")
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, sort_keys=False)

    ns = argparse.Namespace(config=cfg_path, policy=ckpt_path, ablation=ablation)
    before = {d for d in os.listdir(RUNS_DIR)} if os.path.isdir(RUNS_DIR) else set()
    sink = io.StringIO()
    ctx = contextlib.nullcontext() if verbose else contextlib.redirect_stdout(sink)
    with ctx:
        cli.run_policy(ns)
    run_dir = study._find_run_dir("policy", before, cfg_path)
    if run_dir is None:
        return None
    return study.parse_run(name, seed, run_dir)


# --------------------------------------------------------------------------- #
# Aggregation and writers
# --------------------------------------------------------------------------- #
def aggregate_condition(
    name: str,
    label: str,
    frac: Optional[float],
    ablation: str,
    runs: List[study.RunMetrics],
) -> Dict[str, Any]:
    """Aggregate per-seed runs of one condition into a summary row."""
    n = len(runs)
    per_seed_M = [r.M_median for r in runs if r.M_median == r.M_median]
    nc1_k = sum(1 for r in runs if r.nc1_pass)
    valid_k = sum(1 for r in runs if r.valid)
    reasons: Dict[str, int] = {}
    for r in runs:
        for reason in set(r.invalidations):
            reasons[reason] = reasons.get(reason, 0) + 1
    return {
        "name": name,
        "label": label,
        "frac": frac,
        "ablation": ablation,
        "n_seeds": n,
        "valid_rate": (valid_k / n) if n else float("nan"),
        "valid_ci": study.wilson_ci(valid_k, n),
        "M_mean": (float(np.mean(per_seed_M)) if per_seed_M else float("nan")),
        "M_ci": study.bootstrap_ci(per_seed_M),
        "M_median_overall": (float(np.median(per_seed_M)) if per_seed_M else float("nan")),
        "M_per_seed": per_seed_M,
        "nc1_pass_rate": (nc1_k / n) if n else float("nan"),
        "nc1_ci": study.wilson_ci(nc1_k, n),
        "nc1_window_frac_mean": (float(np.mean([r.nc1_window_frac for r in runs])) if runs else float("nan")),
        "invalidation_reasons": reasons,
    }


def write_csv(aggs: List[Dict[str, Any]], path: str) -> None:
    """Write the per-condition aggregates as a flat CSV."""
    import csv

    os.makedirs(os.path.dirname(path), exist_ok=True)
    cols = [
        "condition",
        "label",
        "frac",
        "ablation",
        "n_seeds",
        "valid_rate",
        "M_mean_db",
        "M_lo",
        "M_hi",
        "M_median_db",
        "nc1_pass_rate",
        "nc1_lo",
        "nc1_hi",
        "nc1_window_frac_mean",
        "invalidations",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for a in aggs:
            w.writerow(
                [
                    a["name"],
                    a["label"],
                    ("" if a["frac"] is None else f"{a['frac']:.2f}"),
                    a["ablation"],
                    a["n_seeds"],
                    f"{a['valid_rate']:.4f}",
                    f"{a['M_mean']:.4f}",
                    f"{a['M_ci'][0]:.4f}",
                    f"{a['M_ci'][1]:.4f}",
                    f"{a['M_median_overall']:.4f}",
                    f"{a['nc1_pass_rate']:.4f}",
                    f"{a['nc1_ci'][0]:.4f}",
                    f"{a['nc1_ci'][1]:.4f}",
                    f"{a['nc1_window_frac_mean']:.4f}",
                    ";".join(f"{k}={v}" for k, v in a["invalidation_reasons"].items()),
                ]
            )


# --------------------------------------------------------------------------- #
# Figure
# --------------------------------------------------------------------------- #
def fig_emergence(data: Dict[str, Any], out_dir: str, stem: str = "fig_emergence") -> Optional[str]:
    """Render the emergence figure: training curve and M versus training.

    Panel (a) is the training reward curve (mean episode reward of the ES
    center per generation) with the measured checkpoints marked. Panel (b)
    is the per-seed median loop dominance ``M`` at each checkpoint
    (box plus per-seed points, like the NC1 contrast figure), with the two
    state-independent ablations of the final policy at the right and the
    ``Mmin`` and 0 dB reference lines.

    Args:
        data: Loaded ``emergence_results.json`` payload.
        out_dir: Output directory for the figure files.
        stem: Output file stem.

    Returns:
        Path to the written PNG, or ``None`` if there is nothing to plot.
    """
    import matplotlib.pyplot as plt

    from ldtc.reporting.style import COLORS, apply_matplotlib_theme

    aggs: List[Dict[str, Any]] = list(data.get("aggregates", []))
    runs: Dict[str, List[Dict[str, Any]]] = data.get("runs", {})
    ckpt_aggs = sorted((a for a in aggs if a["ablation"] == "none"), key=lambda a: float(a["frac"]))
    abl_aggs = [a for a in aggs if a["ablation"] != "none"]
    if not ckpt_aggs:
        return None

    mmin = 3.0
    for rows in runs.values():
        if rows:
            mmin = float(rows[0].get("Mmin_db", mmin))
            break

    history = (data.get("meta", {}).get("training_log", {}) or {}).get("history", [])
    ckpt_gens = {
        int(round(100 * float(a["frac"]))): int(a.get("generation", -1))
        for a in ckpt_aggs
        if a.get("generation") is not None
    }

    apply_matplotlib_theme("paper")
    fig, (ax_a, ax_b) = plt.subplots(
        1,
        2,
        figsize=(10.2, 4.0),
        gridspec_kw={"width_ratios": [1.0, 1.5]},
    )

    # Panel (a): training curve.
    if history:
        gens = [h["gen"] for h in history]
        fit = [h["fitness"] for h in history]
        ax_a.plot(gens, fit, color=COLORS["blue"], linewidth=1.8, zorder=3, label="mean episode reward")
        marked = False
        for g in sorted(set(ckpt_gens.values())):
            if g < 0:
                continue
            ax_a.axvline(g, color=COLORS["gray"], linestyle=":", linewidth=1.0, zorder=1)
            if not marked:
                ax_a.axvline(g, color=COLORS["gray"], linestyle=":", linewidth=1.0, zorder=1, label="checkpoint")
                marked = True
        ax_a.set_xlabel("Training generation")
        ax_a.set_ylabel("Mean episode reward")
        ax_a.set_title("(a) Survival training (ES)")
        ax_a.legend(loc="lower right", frameon=False, fontsize=8)

    # Panel (b): M versus training progress, with ablations.
    order = [a["name"] for a in ckpt_aggs] + [a["name"] for a in abl_aggs]
    labels = [a["label"] for a in ckpt_aggs] + [a["label"].replace("ablate: ", "ablate:\n") for a in abl_aggs]
    rng = np.random.default_rng(7)
    for i, a in enumerate(ckpt_aggs + abl_aggs):
        ys = [r["M_median"] for r in runs.get(a["name"], []) if r["M_median"] == r["M_median"]]
        if not ys:
            continue
        xs = i + rng.uniform(-0.12, 0.12, size=len(ys))
        passing = float(a.get("nc1_pass_rate", 0.0)) >= 0.5
        color = COLORS["green"] if passing else COLORS["red"]
        ax_b.scatter(xs, ys, s=30, color=color, alpha=0.75, edgecolor="white", linewidth=0.5, zorder=3)
        bp = ax_b.boxplot(
            ys,
            positions=[i],
            widths=0.5,
            vert=True,
            patch_artist=True,
            showfliers=False,
            zorder=2,
        )
        for box in bp["boxes"]:
            box.set(facecolor=COLORS["gray_light"], edgecolor=COLORS["gray"], alpha=0.7)
        for med in bp["medians"]:
            med.set(color=COLORS["gray"], linewidth=2)
    if abl_aggs:
        ax_b.axvline(len(ckpt_aggs) - 0.5, color=COLORS["gray"], linestyle="-", linewidth=0.8, zorder=1)
    ax_b.axhline(0.0, color=COLORS["gray"], linestyle="-", linewidth=1.0, zorder=1)
    ax_b.axhline(mmin, color=COLORS["blue"], linestyle="--", linewidth=1.5, zorder=1)
    ax_b.text(
        len(order) - 0.5,
        mmin,
        f"  $M_{{\\min}}$ = {mmin:.1f} dB",
        color=COLORS["blue"],
        va="bottom",
        ha="right",
        fontsize=9,
    )
    ax_b.set_xticks(range(len(order)))
    ax_b.set_xticklabels(labels, fontsize=8)
    ax_b.set_xlabel("Training progress (fraction of generations)")
    ax_b.set_ylabel(r"Loop dominance $M$ (dB)")
    n = data.get("meta", {}).get("n_seeds", 0)
    ax_b.set_title(f"(b) Measured loop dominance (N={n} seeds)")

    fig.suptitle("Loop dominance emerges under learned self-maintenance", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.95))

    os.makedirs(out_dir, exist_ok=True)
    base = os.path.join(out_dir, stem)
    fig.savefig(base + ".png", dpi=300, bbox_inches="tight")
    fig.savefig(base + ".pdf", bbox_inches="tight")
    fig.savefig(base + ".svg", bbox_inches="tight")
    plt.close(fig)
    return base + ".png"


def make_figure(out_dir: str) -> Optional[str]:
    """Regenerate the emergence figure from an existing results payload.

    Args:
        out_dir: Directory containing ``emergence_results.json``.

    Returns:
        Path to the written PNG, or ``None``.
    """
    path = os.path.join(out_dir, "emergence_results.json")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return fig_emergence(data, os.path.join(out_dir, "figures"))


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
def run_sweep(
    config: str,
    ckpt_dir: str,
    out_dir: str,
    seeds: List[int],
    ablations: Tuple[str, ...] = ABLATIONS,
    threshold_profile: Optional[str] = None,
    verbose: bool = False,
) -> Dict[str, Any]:
    """Measure every checkpoint (and the final-policy ablations) across seeds.

    Args:
        config: Base profile path (the emergence plant).
        ckpt_dir: Directory of policy checkpoints.
        out_dir: Output directory for results and figures.
        seeds: Seeds to use as replicates.
        ablations: Ablation modes to run at the final checkpoint.
        threshold_profile: Optional calibrated profile whose ``Mmin_db``,
            ``epsilon``, and ``tau_max`` override the base config (R*).
        verbose: If True, let handlers print.

    Returns:
        The full results payload (also written to
        ``emergence_results.json``).
    """
    os.environ["LDTC_SKIP_REPORT"] = "1"  # skip per-run figure bundles
    os.makedirs(RUNS_DIR, exist_ok=True)
    ckpts = discover_checkpoints(ckpt_dir)
    with open(config, "r", encoding="utf-8") as f:
        base_cfg = dict(yaml.safe_load(f) or {})
    overrides = dict(DEFAULT_OVERRIDES)
    if threshold_profile:
        overrides = _apply_rstar(overrides, threshold_profile)

    # Conditions: every checkpoint closed-loop, then ablations of the final.
    conditions: List[Dict[str, Any]] = []
    for ck in ckpts:
        conditions.append({**ck, "ablation": "none"})
    for ab in ablations:
        conditions.append({**ckpts[-1], "ablation": ab})

    runs_by_cond: Dict[str, List[study.RunMetrics]] = {}
    t0 = time.time()
    with tempfile.TemporaryDirectory(prefix="ldtc_emergence_") as tmpdir:
        for cond in conditions:
            frac = float(cond["frac"])
            ablation = str(cond["ablation"])
            name = condition_name(frac, ablation)
            rows: List[study.RunMetrics] = []
            for seed in seeds:
                ts = time.time()
                rm = run_one_policy(
                    base_cfg,
                    overrides,
                    str(cond["path"]),
                    ablation,
                    frac,
                    seed,
                    tmpdir,
                    verbose=verbose,
                )
                dt = time.time() - ts
                if rm is None:
                    print(f"  [{name}] seed={seed}: NO RUN DIR FOUND", flush=True)
                    continue
                rows.append(rm)
                print(
                    f"  [{name}] seed={seed} ({dt:.1f}s): valid={rm.valid} NC1={rm.nc1_pass} "
                    f"M~{rm.M_median:+.1f} (windows {100 * rm.nc1_window_frac:.0f}% cert)",
                    flush=True,
                )
            runs_by_cond[name] = rows
            print(f"== {name}: {len(rows)}/{len(seeds)} runs ==", flush=True)

    aggs: List[Dict[str, Any]] = []
    for cond in conditions:
        frac = float(cond["frac"])
        ablation = str(cond["ablation"])
        name = condition_name(frac, ablation)
        if ablation != "none":
            label = f"ablate: {ablation}"
            agg_frac: Optional[float] = None
        else:
            label = f"{int(round(100 * frac))}%"
            agg_frac = frac
        agg = aggregate_condition(name, label, agg_frac, ablation, runs_by_cond.get(name, []))
        agg["generation"] = int(cond.get("generation", -1))
        aggs.append(agg)

    training_log: Dict[str, Any] = {}
    tl_path = os.path.join(os.path.dirname(os.path.abspath(ckpt_dir)), "training_log.json")
    if os.path.exists(tl_path):
        with open(tl_path, "r", encoding="utf-8") as f:
            training_log = json.load(f)

    thr_label = os.path.relpath(threshold_profile or config, REPO_ROOT)
    payload: Dict[str, Any] = {
        "meta": {
            "seeds": seeds,
            "n_seeds": len(seeds),
            "config": os.path.relpath(config, REPO_ROOT),
            "threshold_profile": thr_label,
            "ckpt_dir": os.path.relpath(ckpt_dir, REPO_ROOT),
            "overrides": overrides,
            "elapsed_sec": round(time.time() - t0, 1),
            "timestamp": time.time(),
            "training_log": training_log,
        },
        "aggregates": aggs,
        "runs": {name: [asdict(r) for r in rs] for name, rs in runs_by_cond.items()},
    }
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "emergence_results.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    write_csv(aggs, os.path.join(out_dir, "emergence_results.csv"))
    return payload


def print_summary(payload: Dict[str, Any]) -> None:
    """Print a compact human-readable summary to stdout."""
    print("\n=== EMERGENCE SUMMARY ===")
    for a in payload["aggregates"]:
        print(
            f"{a['label']:>16s}  valid={100 * a['valid_rate']:3.0f}%  NC1={100 * a['nc1_pass_rate']:3.0f}%  "
            f"M={a['M_mean']:+6.1f} dB [{a['M_ci'][0]:+.1f},{a['M_ci'][1]:+.1f}]  "
            f"(windows {100 * a['nc1_window_frac_mean']:3.0f}% cert)"
        )


def main() -> None:
    """CLI entry point for the emergence measurement sweep."""
    ap = argparse.ArgumentParser(description="Measure policy checkpoints with the production harness.")
    ap.add_argument("--config", type=str, default=os.path.join(REPO_ROOT, "configs", "profile_emergence.yml"))
    ap.add_argument("--ckpt-dir", type=str, default=os.path.join(REPO_ROOT, "artifacts", "emergence", "checkpoints"))
    ap.add_argument("--out", type=str, default=os.path.join(REPO_ROOT, "artifacts", "emergence"))
    ap.add_argument("--seeds", type=int, default=15, help="Number of seeds (replicates) per condition.")
    ap.add_argument("--seed-base", type=int, default=3000, help="First seed; seeds are base..base+N-1.")
    ap.add_argument(
        "--rstar",
        nargs="?",
        const=os.path.join(REPO_ROOT, "configs", "profile_rstar.yml"),
        default="",
        help="Evaluate against calibrated R* thresholds from this profile "
        "(default configs/profile_rstar.yml). Requires running calibrate first.",
    )
    ap.add_argument("--no-ablations", action="store_true", help="Skip the final-checkpoint ablation runs.")
    ap.add_argument("--no-figures", action="store_true", help="Skip figure generation.")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if args.rstar and not os.path.exists(args.rstar):
        ap.error(f"--rstar profile not found: {args.rstar} (run `make calibrate` first)")

    seeds = [args.seed_base + i for i in range(int(args.seeds))]
    ablations: Tuple[str, ...] = () if args.no_ablations else ABLATIONS
    if args.rstar:
        print(f"Evaluating against calibrated thresholds from {args.rstar}", flush=True)
    print(f"Emergence sweep: checkpoints in {args.ckpt_dir} x {len(seeds)} seeds -> {args.out}", flush=True)

    payload = run_sweep(
        config=args.config,
        ckpt_dir=args.ckpt_dir,
        out_dir=args.out,
        seeds=seeds,
        ablations=ablations,
        threshold_profile=(args.rstar or None),
        verbose=args.verbose,
    )
    print_summary(payload)

    if not args.no_figures:
        try:
            p = fig_emergence(payload, os.path.join(args.out, "figures"))
            if p:
                print(f"  figure: {p}")
        except Exception as exc:  # pragma: no cover - figures are best-effort
            print(f"(figure skipped: {exc})")

    print(f"\nWrote: {os.path.join(args.out, 'emergence_results.json')}")
    print(f"Wrote: {os.path.join(args.out, 'emergence_results.csv')}")


if __name__ == "__main__":
    main()
