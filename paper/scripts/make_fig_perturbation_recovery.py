#!/usr/bin/env python3
"""Generate perturbation–recovery timeline (numberless names).

Outputs: paper/figures/fig_perturbation_recovery.{pdf,png,svg}
"""
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt

from ldtc.reporting.style import COLORS, apply_matplotlib_theme


def main() -> None:
    here = Path(__file__).resolve().parent.parent
    figures_dir = here / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    # Apply shared theme
    apply_matplotlib_theme("paper")

    # Colors / styling
    color_phi_loop = COLORS["green"]
    color_phi_exchange = COLORS["gray"]
    color_perturbation = COLORS["gray_light"]
    color_text = "#34495E"

    plt.rcParams.update(
        {
            "axes.edgecolor": color_text,
            "xtick.color": color_text,
            "ytick.color": color_text,
            "axes.labelcolor": color_text,
            "axes.titlecolor": color_text,
        }
    )

    # Data (seeded for reproducibility)
    rng = np.random.default_rng(0)
    t = np.linspace(0, 100, 500)
    phi_exchange_level = 50.0
    phi_loop_baseline = 80.0

    phi_exchange = np.full_like(t, phi_exchange_level) + rng.normal(0.0, 0.5, t.shape)

    phi_loop = np.full_like(t, phi_loop_baseline)
    perturbation_start, perturbation_end = 30.0, 50.0
    dip_time, dip_depth, recovery_rate = 38.0, 45.0, 0.1

    dip = dip_depth * np.exp(-((t - dip_time) ** 2) / 8.0)
    phi_loop = phi_loop - dip

    start_idx = int(np.searchsorted(t, dip_time, side="right"))
    for i in range(start_idx, len(t)):
        if phi_loop[i] < phi_loop_baseline:
            phi_loop[i] = min(
                phi_loop[i - 1] + recovery_rate * (phi_loop_baseline - phi_loop[i - 1]),
                phi_loop_baseline,
            )

    pre_idx = int(np.searchsorted(t, perturbation_start, side="right"))
    phi_loop[:pre_idx] = phi_loop_baseline

    # Plot
    fig, ax = plt.subplots(figsize=(6.5, 4.0))

    # Use mathtext for \mathcal{L} to avoid missing glyphs in Helvetica
    ax.plot(
        t,
        phi_loop,
        label=r"$\mathcal{L}_{\mathrm{loop}}$ (Self-Maintenance)",
        color=color_phi_loop,
        linewidth=3,
        zorder=10,
    )

    ax.plot(
        t,
        phi_exchange,
        label=r"$\mathcal{L}_{\mathrm{exchange}}$ (External Tasks)",
        color=color_phi_exchange,
        linestyle="--",
        linewidth=2,
        zorder=5,
    )

    ax.axvspan(
        perturbation_start,
        perturbation_end,
        facecolor=color_perturbation,
        alpha=0.7,
        zorder=0,
        label="Bounded Disturbance Window",
    )

    # Annotations
    ax.annotate(
        "Perturbation\nOnset",
        xy=(perturbation_start, phi_loop_baseline + 2.0),
        xytext=(15, 95),
        arrowprops=dict(facecolor=color_text, shrink=0.05, width=1.5, headwidth=8),
        ha="center",
        va="center",
        fontsize=10,
        weight="bold",
        color=color_text,
    )

    ax.annotate(
        "Loop-Power Dip",
        xy=(dip_time, float(np.min(phi_loop))),
        xytext=(dip_time, 10),
        arrowprops=dict(facecolor=color_text, shrink=0.05, width=1.5, headwidth=8),
        ha="center",
        va="center",
        fontsize=10,
        weight="bold",
        color=color_text,
    )

    ax.annotate(
        "Autonomous Recovery",
        xy=(55, 60),
        xytext=(70, 40),
        arrowprops=dict(facecolor=color_text, shrink=0.05, width=1.5, headwidth=8),
        ha="center",
        va="center",
        fontsize=10,
        weight="bold",
        color=color_text,
    )

    after_dip = (t > dip_time) & (phi_loop > phi_exchange)
    idxs = np.where(after_dip)[0]
    recovery_idx = int(idxs[0]) if idxs.size else len(t) - 1
    ax.annotate(
        "Return to Baseline\n(NC1 Restored)",
        xy=(t[recovery_idx], phi_loop[recovery_idx]),
        xytext=(min(t[recovery_idx] + 15, 98), 75),
        arrowprops=dict(facecolor=color_text, shrink=0.05, width=1.5, headwidth=8),
        ha="center",
        va="center",
        fontsize=10,
        weight="bold",
        color=color_text,
    )

    # Threshold + inequality (use ℒ with math subscripts)
    ax.axhline(
        y=phi_exchange_level, color=color_phi_exchange, linestyle=":", linewidth=1.5
    )
    ax.text(
        98,
        phi_exchange_level - 5,
        r"NC1 Threshold: $\mathcal{L}_{\mathrm{loop}}$ > $\mathcal{L}_{\mathrm{exchange}}$",
        ha="right",
        va="center",
        fontsize=10,
        color=color_phi_exchange,
        style="italic",
    )

    # Finish
    ax.set_xlabel("Time (Arbitrary Units)")
    ax.set_ylabel(r"Integrated Causal Power ($\mathcal{L}$)")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_ylim(0, 110)
    ax.set_xlim(0, 100)
    ax.set_yticks([])
    ax.legend(loc="upper right", frameon=False)

    fig.tight_layout()

    out_pdf = figures_dir / "fig_perturbation_recovery.pdf"
    out_png = figures_dir / "fig_perturbation_recovery.png"
    out_svg = figures_dir / "fig_perturbation_recovery.svg"
    fig.savefig(out_pdf, bbox_inches="tight")
    fig.savefig(out_png, dpi=300, bbox_inches="tight")
    fig.savefig(out_svg, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out_pdf}")


if __name__ == "__main__":
    main()
