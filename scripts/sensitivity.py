#!/usr/bin/env python3
"""Scripts: Sensitivity sweeps for the NC1 loop-dominance result.

Shows that the headline contrast (positive control ``M`` well above ``Mmin``;
controller-disabled negative control ``M`` below 0) is robust to the main
measurement and model choices. For each swept setting the script runs the
positive control and the controller-disabled negative control across several
seeds (via the production harness) and reports the seed-mean median ``M`` with
a bootstrap CI.

Axes swept:

* ``p_lag``: VAR lag order of the linear estimator.
* ``window_sec``: measurement window length.
* ``method``: estimator family (linear VAR-Granger vs. mutual information).
* ``coupling``: a multiplicative scale on the plant's internal self-maintenance
  coupling (``c_TE``, ``c_RT``, ``c_RE``).

Outputs ``sensitivity_results.{json,csv,tex}`` and ``fig_sensitivity.{png,pdf,svg}``.

Run:

    python scripts/sensitivity.py --seeds 4 --out artifacts/sensitivity

See Also:
    paper/main.tex: Results: Sensitivity analysis.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List

import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import study  # noqa: E402

# Plant coupling defaults (see ldtc/plant/models.py PlantParams).
BASE_COUPLING = {"c_TE": 0.90, "c_RT": 0.54, "c_RE": 0.66}

# Speed overrides applied to every sweep run (the CI comes from across seeds,
# so each run can be shorter than a headline study run).
SPEED = {"baseline_sec": 8.0, "diag_cadence_windows": 100, "n_boot": 24}


@dataclass
class Setting:
    """One point in a sensitivity sweep."""

    axis: str
    label: str
    overrides: Dict[str, Any] = field(default_factory=dict)


def build_settings() -> List[Setting]:
    """Construct the full list of sweep settings."""
    settings: List[Setting] = []
    for p in (2, 3, 4):
        settings.append(Setting("p_lag", str(p), {"p_lag": p, **SPEED}))
    for w in (2.0, 3.0, 4.0):
        settings.append(Setting("window_sec", f"{w:.0f}s", {"window_sec": w, **SPEED}))
    for m in ("linear", "mi"):
        # MI is heavier per window; keep its bootstrap modest.
        extra = {"n_boot": 12} if m == "mi" else {}
        settings.append(Setting("method", m, {"method": m, **SPEED, **extra}))
    for s in (0.7, 1.0, 1.3):
        coup = {k: round(v * s, 4) for k, v in BASE_COUPLING.items()}
        settings.append(Setting("coupling", f"x{s:.1f}", {"plant": {"params": coup}, **SPEED}))
    return settings


def _scn_with(base: "study.Scenario", overrides: Dict[str, Any]) -> "study.Scenario":
    merged = dict(base.overrides)
    merged.update(overrides)
    return study.Scenario(
        name=base.name,
        label=base.label,
        kind=base.kind,
        expectation=base.expectation,
        handler=base.handler,
        config=base.config,
        run_tag=base.run_tag,
        omega_args=dict(base.omega_args),
        overrides=merged,
    )


def run_sweeps(seeds: List[int], out_dir: str) -> Dict[str, Any]:
    """Run every sweep setting for the positive and negative controls.

    Args:
        seeds: Replicate seeds.
        out_dir: Output directory for results.

    Returns:
        The results payload (also written to ``sensitivity_results.json``).
    """
    os.environ["LDTC_SKIP_REPORT"] = "1"
    scen = {s.name: s for s in study.default_scenarios()}
    pos = scen["positive"]
    neg = scen["neg_controller_disabled"]
    settings = build_settings()

    rows: List[Dict[str, Any]] = []
    t0 = time.time()
    with tempfile.TemporaryDirectory(prefix="ldtc_sens_") as tmp:
        for st in settings:
            row: Dict[str, Any] = {"axis": st.axis, "label": st.label}
            for tag, base in (("pos", pos), ("neg", neg)):
                scn = _scn_with(base, st.overrides)
                meds: List[float] = []
                npass = 0
                nvalid = 0
                for seed in seeds:
                    rm = study.run_one(scn, seed, tmp)
                    if rm is None:
                        continue
                    if rm.valid:
                        nvalid += 1
                    if rm.M_median == rm.M_median:
                        meds.append(rm.M_median)
                    if rm.nc1_pass:
                        npass += 1
                mean = float(np.mean(meds)) if meds else float("nan")
                lo, hi = study.bootstrap_ci(meds)
                row[f"{tag}_M_mean"] = mean
                row[f"{tag}_M_lo"] = lo
                row[f"{tag}_M_hi"] = hi
                row[f"{tag}_nc1_rate"] = npass / len(seeds) if seeds else float("nan")
                row[f"{tag}_valid_rate"] = nvalid / len(seeds) if seeds else float("nan")
            rows.append(row)
            print(
                f"  [{st.axis}={st.label}] pos M={row['pos_M_mean']:+.1f} "
                f"[{row['pos_M_lo']:+.1f},{row['pos_M_hi']:+.1f}]  "
                f"neg M={row['neg_M_mean']:+.1f} [{row['neg_M_lo']:+.1f},{row['neg_M_hi']:+.1f}]",
                flush=True,
            )

    payload = {
        "meta": {"seeds": seeds, "n_seeds": len(seeds), "elapsed_sec": round(time.time() - t0, 1)},
        "rows": rows,
    }
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "sensitivity_results.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    _write_csv(rows, os.path.join(out_dir, "sensitivity_results.csv"))
    _write_latex(rows, os.path.join(out_dir, "sensitivity_results.tex"), len(seeds))
    return payload


def _write_csv(rows: List[Dict[str, Any]], path: str) -> None:
    import csv

    cols = [
        "axis",
        "label",
        "pos_M_mean",
        "pos_M_lo",
        "pos_M_hi",
        "pos_nc1_rate",
        "pos_valid_rate",
        "neg_M_mean",
        "neg_M_lo",
        "neg_M_hi",
        "neg_nc1_rate",
        "neg_valid_rate",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow([r.get(c, "") for c in cols])


def _write_latex(rows: List[Dict[str, Any]], path: str, n_seeds: int) -> None:
    lines = [
        "% Auto-generated by scripts/sensitivity.py -- do not edit by hand.",
        "\\begin{tabular}{llcc}",
        "\\toprule",
        "Axis & Setting & Positive $M$ (dB) & Loop-ablated $M$ (dB) \\\\",
        "\\midrule",
    ]
    # Display labels keep the table free of raw underscores (LaTeX text mode).
    axis_label = {
        "p_lag": "VAR lag $p$",
        "window_sec": "Window",
        "method": "Estimator",
        "coupling": "Coupling scale",
    }
    last_axis = None
    for r in rows:
        axis = axis_label.get(r["axis"], r["axis"]) if r["axis"] != last_axis else ""
        last_axis = r["axis"]
        pos = f"{r['pos_M_mean']:+.1f} [{r['pos_M_lo']:+.1f}, {r['pos_M_hi']:+.1f}]"
        neg = f"{r['neg_M_mean']:+.1f} [{r['neg_M_lo']:+.1f}, {r['neg_M_hi']:+.1f}]"
        lines.append(f"{axis} & {r['label']} & {pos} & {neg} \\\\")
    lines += [
        "\\bottomrule",
        "\\end{tabular}",
        f"% N = {n_seeds} seeds per cell; brackets are 95% bootstrap CIs on the mean of per-seed median M.",
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def make_figure(payload: Dict[str, Any], out_dir: str) -> str:
    """Render a 2x2 robustness figure (one panel per swept axis)."""
    import matplotlib.pyplot as plt

    from ldtc.reporting.style import COLORS, apply_matplotlib_theme

    rows = payload["rows"]
    axes_order = ["p_lag", "window_sec", "method", "coupling"]
    titles = {
        "p_lag": "VAR lag $p$",
        "window_sec": "Window length",
        "method": "Estimator",
        "coupling": "Internal coupling scale",
    }
    # The robustness claim is the sign of the contrast: positive control above
    # the loop/exchange dominance boundary (M=0), controller-disabled below it.
    # We deliberately do not draw a single Mmin line here because the calibrated
    # threshold is estimator-specific (the MI and linear scales differ), so one
    # line would be misleading across the estimator panel.
    apply_matplotlib_theme("paper")
    fig, axs = plt.subplots(2, 2, figsize=(9.0, 6.4))
    for ax, axis in zip(axs.ravel(), axes_order):
        sub = [r for r in rows if r["axis"] == axis]
        if not sub:
            ax.set_visible(False)
            continue
        x = np.arange(len(sub))
        labels = [r["label"] for r in sub]
        pos = np.array([r["pos_M_mean"] for r in sub])
        pos_lo = np.array([r["pos_M_mean"] - r["pos_M_lo"] for r in sub])
        pos_hi = np.array([r["pos_M_hi"] - r["pos_M_mean"] for r in sub])
        neg = np.array([r["neg_M_mean"] for r in sub])
        neg_lo = np.array([r["neg_M_mean"] - r["neg_M_lo"] for r in sub])
        neg_hi = np.array([r["neg_M_hi"] - r["neg_M_mean"] for r in sub])
        ax.errorbar(
            x - 0.06, pos, yerr=[pos_lo, pos_hi], fmt="o-", color=COLORS["green"], capsize=4, label="positive", zorder=3
        )
        ax.errorbar(
            x + 0.06,
            neg,
            yerr=[neg_lo, neg_hi],
            fmt="s--",
            color=COLORS["red"],
            capsize=4,
            label="loop ablated",
            zorder=3,
        )
        ax.axhline(
            0.0, color=COLORS["gray"], linestyle="-", linewidth=1.0, zorder=1, label="dominance boundary ($M=0$)"
        )
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        ax.set_title(titles.get(axis, axis))
        ax.set_ylabel(r"$M$ (dB)")
    axs.ravel()[0].legend(frameon=False, fontsize=8, loc="center right")
    fig.suptitle("NC1 loop dominance is robust to estimator and model choices", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    base = os.path.join(out_dir, "fig_sensitivity")
    for ext in ("png", "pdf", "svg"):
        fig.savefig(base + "." + ext, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return base + ".png"


def main() -> None:
    """CLI entry point for the sensitivity sweeps."""
    ap = argparse.ArgumentParser(description="Run NC1 sensitivity sweeps and emit table + figure.")
    ap.add_argument("--seeds", type=int, default=4)
    ap.add_argument("--seed-base", type=int, default=60000)
    ap.add_argument("--out", type=str, default=os.path.join(REPO_ROOT, "artifacts", "sensitivity"))
    ap.add_argument("--no-figure", action="store_true")
    args = ap.parse_args()

    seeds = [args.seed_base + i for i in range(int(args.seeds))]
    print(f"Sensitivity sweeps: {len(build_settings())} settings x {len(seeds)} seeds", flush=True)
    payload = run_sweeps(seeds, args.out)
    if not args.no_figure:
        try:
            p = make_figure(payload, args.out)
            print(f"  figure: {p}")
        except Exception as exc:  # pragma: no cover
            print(f"(figure skipped: {exc})")
    print(f"Wrote: {os.path.join(args.out, 'sensitivity_results.json')}")


if __name__ == "__main__":
    main()
