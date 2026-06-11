#!/usr/bin/env python3
"""Scripts: Figures for the multi-seed LDTC study.

Consumes ``study_results.json`` (written by :mod:`study`) plus the per-run
audit logs it references, and emits the paper's results figures:

* ``fig_nc1_contrast``: per-seed median loop dominance ``M`` (dB) for the
  positive control and the negative controls, with the ``Mmin`` and 0 dB
  reference lines (the headline NC1 result).
* ``fig_pass_rates``: NC1 / SC1 / refusal pass-rates per scenario with Wilson
  95% CIs.
* ``fig_sc1_recovery``: a real ``M(t)`` trajectory from a representative
  power-sag run, with the perturbation window shaded (replaces the previous
  hand-drawn placeholder).

All figures are written as PNG, PDF, and SVG into ``<study_dir>/figures``.

See Also:
    paper/main.tex: Results.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np

from ldtc.reporting.style import COLORS, apply_matplotlib_theme

SHORT_LABELS = {
    "positive": "Positive\ncontrol",
    "neg_controller_disabled": "Loop\nablated",
    "neg_permanent_ex_flood": "Sustained\nex-flood",
    "neg_exogenous_subsidy": "Exogenous\nsubsidy",
    "sc1_power_sag": "Power\nsag",
    "sc1_ingress_flood": "Ingress\nflood",
    "sc1_control_outage": "Control\noutage",
    "refusal_command_conflict": "Command\nconflict",
    "adv_replay_controller": "Replayed\nactuation",
    "adv_hidden_tether": "Hidden\ntether",
    "adv_oscillator": "Oscillator\ninflation",
}


def _save(fig: "plt.Figure", out_dir: str, stem: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.join(out_dir, stem)
    fig.savefig(base + ".png", dpi=300, bbox_inches="tight")
    fig.savefig(base + ".pdf", bbox_inches="tight")
    fig.savefig(base + ".svg", bbox_inches="tight")
    plt.close(fig)
    return base + ".png"


def _load(study_dir: str) -> Dict[str, Any]:
    with open(os.path.join(study_dir, "study_results.json"), "r", encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------- #
# Figure 1: NC1 contrast (per-seed median M by scenario)
# --------------------------------------------------------------------------- #
def fig_nc1_contrast(data: Dict[str, Any], out_dir: str, stem: str = "fig_nc1_contrast") -> Optional[str]:
    """Per-seed median ``M`` for the positive and negative controls."""
    order = ["positive", "neg_controller_disabled", "neg_permanent_ex_flood"]
    runs = data.get("runs", {})
    aggs = {a["name"]: a for a in data.get("aggregates", [])}
    present = [s for s in order if s in runs and runs[s]]
    if not present:
        return None

    mmin = 3.0
    for s in present:
        rs = runs[s]
        if rs:
            mmin = float(rs[0].get("Mmin_db", 3.0))
            break

    apply_matplotlib_theme("paper")
    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    rng = np.random.default_rng(7)
    for i, s in enumerate(present):
        ys = [r["M_median"] for r in runs[s] if r["M_median"] == r["M_median"]]
        if not ys:
            continue
        xs = i + rng.uniform(-0.12, 0.12, size=len(ys))
        pos = aggs.get(s, {}).get("M_mean", float("nan")) >= mmin
        color = COLORS["green"] if pos else COLORS["red"]
        ax.scatter(xs, ys, s=34, color=color, alpha=0.75, edgecolor="white", linewidth=0.5, zorder=3)
        # Box (median + IQR) for the scenario.
        bp = ax.boxplot(
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

    ax.axhline(0.0, color=COLORS["gray"], linestyle="-", linewidth=1.0, zorder=1)
    ax.axhline(mmin, color=COLORS["blue"], linestyle="--", linewidth=1.5, zorder=1)
    ax.text(
        len(present) - 0.5,
        mmin,
        f"  $M_{{\\min}}$ = {mmin:.0f} dB",
        color=COLORS["blue"],
        va="bottom",
        ha="right",
        fontsize=9,
    )
    ax.set_xticks(range(len(present)))
    ax.set_xticklabels([SHORT_LABELS.get(s, s) for s in present])
    ax.set_ylabel(r"Loop dominance $M$ (dB)")
    ax.set_title("NC1 contrast: loop dominance across controls")
    n = data.get("meta", {}).get("n_seeds", len(runs[present[0]]))
    ax.text(
        0.99,
        0.02,
        f"each point = 1 seed (N={n})",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=8,
        color=COLORS["gray"],
    )
    fig.tight_layout()
    return _save(fig, out_dir, stem)


# --------------------------------------------------------------------------- #
# Figure 2: pass-rates with Wilson CIs
# --------------------------------------------------------------------------- #
def fig_outcomes(data: Dict[str, Any], out_dir: str) -> Optional[str]:
    """Fraction of seeds whose outcome matched the theory's prediction.

    Each scenario is scored against its *expected* outcome (positive control
    passes NC1; negative controls fail NC1 or are invalidated; SC1 scenarios
    recover; the command conflict is refused). If the framework behaves as
    predicted, every bar is near 100%. Whiskers are 95% Wilson CIs.
    """
    aggs = {a["name"]: a for a in data.get("aggregates", [])}
    order = [
        "positive",
        "neg_controller_disabled",
        "neg_permanent_ex_flood",
        "neg_exogenous_subsidy",
        "sc1_power_sag",
        "sc1_ingress_flood",
        "sc1_control_outage",
        "refusal_command_conflict",
        "adv_replay_controller",
        "adv_hidden_tether",
        "adv_oscillator",
    ]
    present = [s for s in order if s in aggs]
    if not present:
        return None

    # Adversarial scenarios match the prediction when the harness does NOT
    # certify them: nc1_pass is already (valid AND M >= Mmin), so its
    # complement covers both the NC1-fail and the invalidated-run paths.
    adversarial = {"adv_replay_controller", "adv_hidden_tether", "adv_oscillator"}

    criterion = {
        "positive": "NC1 holds",
        "neg_controller_disabled": "NC1 rejected",
        "neg_permanent_ex_flood": "NC1 rejected",
        "neg_exogenous_subsidy": "invalidated",
        "sc1_power_sag": "SC1 holds",
        "sc1_ingress_flood": "SC1 holds",
        "sc1_control_outage": "SC1 rejected",
        "refusal_command_conflict": "refused",
        "adv_replay_controller": "not certified",
        "adv_hidden_tether": "not certified",
        "adv_oscillator": "not certified",
    }

    labels: List[str] = []
    rates: List[float] = []
    los: List[float] = []
    his: List[float] = []
    colors: List[str] = []
    for s in present:
        a = aggs[s]
        if s == "neg_exogenous_subsidy":
            rate = 1.0 - a["valid_rate"]
            ci = (1.0 - a["valid_ci"][1], 1.0 - a["valid_ci"][0])
        elif s in ("neg_controller_disabled", "neg_permanent_ex_flood") or s in adversarial:
            rate = 1.0 - a["nc1_pass_rate"]
            ci = (1.0 - a["nc1_ci"][1], 1.0 - a["nc1_ci"][0])
        elif s == "sc1_control_outage":
            # Designed fail: the prediction is matched when SC1 *rejects*.
            sp = a["sc1_pass_rate"] if a["sc1_pass_rate"] is not None else float("nan")
            rate = 1.0 - sp
            ci = (1.0 - a["sc1_ci"][1], 1.0 - a["sc1_ci"][0]) if a["sc1_ci"] else (rate, rate)
        elif a["kind"] == "nc1":
            rate = a["nc1_pass_rate"]
            ci = tuple(a["nc1_ci"])
        elif a["kind"] == "sc1":
            rate = a["sc1_pass_rate"] if a["sc1_pass_rate"] is not None else float("nan")
            ci = tuple(a["sc1_ci"]) if a["sc1_ci"] else (rate, rate)
        else:  # refusal
            rate = a["refusal_rate"] if a["refusal_rate"] is not None else float("nan")
            ci = tuple(a["refusal_ci"]) if a["refusal_ci"] else (rate, rate)
        labels.append(SHORT_LABELS.get(s, s) + f"\n({criterion[s]})")
        rates.append(100.0 * rate)
        los.append(100.0 * (rate - ci[0]))
        his.append(100.0 * (ci[1] - rate))
        colors.append(COLORS["green"] if rate >= 0.5 else COLORS["red"])

    apply_matplotlib_theme("paper")
    fig, ax = plt.subplots(figsize=(max(7.6, 0.95 * len(present)), 4.2))
    x = np.arange(len(present))
    ax.bar(x, rates, width=0.62, color=colors, alpha=0.85, zorder=2)
    ax.errorbar(
        x,
        rates,
        yerr=[los, his],
        fmt="none",
        ecolor=COLORS["gray"],
        elinewidth=1.4,
        capsize=4,
        zorder=3,
    )
    for xi, r in zip(x, rates):
        if r == r:
            ax.text(float(xi), min(r + 2.5, 101), f"{r:.0f}%", ha="center", va="bottom", fontsize=8, color="#34495E")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("Seeds matching prediction (%)")
    ax.set_ylim(0, 108)
    n = data.get("meta", {}).get("n_seeds", 0)
    ax.set_title(f"Predicted outcome confirmed across scenarios (N={n}, 95% Wilson CIs)")
    fig.tight_layout()
    return _save(fig, out_dir, "fig_outcomes")


# --------------------------------------------------------------------------- #
# Figure 3: real SC1 recovery trajectory
# --------------------------------------------------------------------------- #
def _trajectory_from_audit(audit_path: str) -> Tuple[List[float], List[int], Dict[str, int]]:
    """Reconstruct the M(t) series and phase boundaries from an audit log.

    Walks the audit in counter order, tracking the perturbation phase from the
    ``omega_power_sag_*`` markers, and returns the per-window M values, their
    phase code (0 baseline, 1 sag, 2 recovery), and the window indices where
    the sag starts/stops.

    Args:
        audit_path: Path to the run's audit JSONL.

    Returns:
        ``(M_values, phase_codes, markers)`` where ``markers`` has
        ``sag_start`` and ``sag_stop`` window indices.
    """
    ms: List[float] = []
    phases: List[int] = []
    phase = 0
    markers = {"sag_start": -1, "sag_stop": -1}
    with open(audit_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            e = json.loads(line)
            ev = e.get("event", "")
            # The perturbation is bracketed by the "*_window_start"/"*_window_stop"
            # markers (the bare "*_start"/"*_stop" events bracket the whole
            # procedure, including the pre-Ω baseline and post-Ω recovery).
            if ev.endswith("_window_start"):
                phase = 1
                markers["sag_start"] = len(ms)
            elif ev.endswith("_window_stop"):
                phase = 2
                markers["sag_stop"] = len(ms)
            elif ev == "window_measured":
                m = e.get("details", {}).get("M")
                if m is not None:
                    ms.append(float(m))
                    phases.append(phase)
    return ms, phases, markers


def _aggregate_trajectory(data: Dict[str, Any], scenario: str) -> Optional[Dict[str, Any]]:
    """Aggregate per-seed M(window) trajectories for a scenario.

    Aligns all valid runs by window index (the configuration is identical
    across seeds, so the phase boundaries coincide), truncates to the common
    length, and returns the mean trajectory with a 10-90th percentile band.

    Args:
        data: Loaded study results.
        scenario: Scenario key (e.g., ``"sc1_power_sag"``).

    Returns:
        Dict with ``mean``, ``p10``, ``p90``, ``sag_start``, ``sag_stop``,
        ``n``, and ``mmin``; or ``None`` if no trajectories are available.
    """
    runs = data.get("runs", {}).get(scenario, [])
    series: List[List[float]] = []
    starts: List[int] = []
    stops: List[int] = []
    mmin = 3.0
    for r in runs:
        if not r.get("valid", True):
            continue
        ap = os.path.join(r["run_dir"], "audits", "audit.jsonl")
        if not os.path.exists(ap):
            continue
        ms, _ph, mk = _trajectory_from_audit(ap)
        if not ms:
            continue
        series.append(ms)
        starts.append(mk["sag_start"])
        stops.append(mk["sag_stop"])
        mmin = float(r.get("Mmin_db", mmin))
    if not series:
        return None
    L = min(len(s) for s in series)
    arr = np.asarray([s[:L] for s in series], dtype=float)
    good_starts = [s for s in starts if 0 <= s < L]
    good_stops = [s for s in stops if 0 <= s < L]
    return {
        "mean": arr.mean(axis=0),
        "p10": np.percentile(arr, 10, axis=0),
        "p90": np.percentile(arr, 90, axis=0),
        "sag_start": int(np.median(good_starts)) if good_starts else -1,
        "sag_stop": int(np.median(good_stops)) if good_stops else -1,
        "n": len(series),
        "mmin": mmin,
    }


def fig_sc1_recovery(data: Dict[str, Any], out_dir: str, stem: str = "fig_sc1_recovery") -> Optional[str]:
    """Aggregate M(t) trajectories across seeds for the SC1 perturbations.

    One panel per perturbation type (power sag, ingress flood, control
    outage). Each shows the seed-mean loop dominance with a 10-90th percentile
    band, the shaded perturbation window, and the ``Mmin`` reference. The sag
    and flood panels demonstrate bounded-depth recovery (SC1 holds); the
    control-outage panel shows the designed failure (the loop itself is
    ablated, so dominance collapses far beyond the depth bound until the loop
    is restored).
    """
    panels = [
        ("sc1_power_sag", "Power sag"),
        ("sc1_ingress_flood", "Ingress flood"),
        ("sc1_control_outage", "Control outage (designed fail)"),
    ]
    aggs: List[Tuple[str, Dict[str, Any]]] = []
    for name, lbl in panels:
        a = _aggregate_trajectory(data, name)
        if a is not None:
            aggs.append((lbl, a))
    if not aggs:
        return None

    apply_matplotlib_theme("paper")
    fig, axes = plt.subplots(1, len(aggs), figsize=(4.6 * len(aggs), 4.0), sharey=True, squeeze=False)
    for ax, (lbl, a) in zip(axes[0], aggs):
        x = np.arange(len(a["mean"]))
        if a["sag_start"] >= 0:
            stop = a["sag_stop"] if a["sag_stop"] >= 0 else len(a["mean"])
            ax.axvspan(a["sag_start"], stop, color=COLORS["yellow_light"], alpha=0.85, zorder=0, label="Perturbation")
        ax.fill_between(x, a["p10"], a["p90"], color=COLORS["green_light"], alpha=0.7, zorder=2, label="10-90th pct")
        ax.plot(x, a["mean"], color=COLORS["green"], linewidth=2.0, zorder=3, label="seed mean $M$")
        ax.axhline(a["mmin"], color=COLORS["blue"], linestyle="--", linewidth=1.4, zorder=1)
        ax.axhline(0.0, color=COLORS["gray"], linestyle="-", linewidth=0.8, zorder=1)
        ax.text(
            len(a["mean"]) - 1,
            a["mmin"],
            f" $M_{{\\min}}$={a['mmin']:.0f} dB",
            color=COLORS["blue"],
            va="bottom",
            ha="right",
            fontsize=9,
        )
        ax.set_xlabel("Measurement window")
        ax.set_title(f"{lbl} (N={a['n']})")
    axes[0][0].set_ylabel(r"Loop dominance $M$ (dB)")
    axes[0][-1].legend(loc="lower left", frameon=False, fontsize=8)
    fig.suptitle(
        "SC1: bounded perturbations recover; ablating the loop itself does not",
        fontsize=12,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    return _save(fig, out_dir, stem)


def make_all_figures(study_dir: str) -> List[str]:
    """Generate all study figures into ``<study_dir>/figures``.

    Args:
        study_dir: Directory containing ``study_results.json``.

    Returns:
        List of written PNG paths (best-effort; failures are skipped).
    """
    data = _load(study_dir)
    out_dir = os.path.join(study_dir, "figures")
    written: List[str] = []
    for fn in (fig_nc1_contrast, fig_outcomes, fig_sc1_recovery):
        try:
            p = fn(data, out_dir)
            if p:
                written.append(p)
                print(f"  figure: {p}")
        except Exception as exc:  # pragma: no cover - figures are best-effort
            print(f"  (figure {fn.__name__} failed: {exc})")
    return written


if __name__ == "__main__":
    import sys

    d = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "artifacts", "study")
    )
    make_all_figures(d)
