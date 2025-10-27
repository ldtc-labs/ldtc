#!/usr/bin/env python3
"""Generate a simple demo plot.

Creates a damped sinusoid and writes ``paper/figures/fig_hello.{pdf,png,svg}``.
"""
from pathlib import Path

import matplotlib.pyplot as plt

from ldtc.reporting.style import COLORS, apply_matplotlib_theme
import numpy as np


def main() -> None:
    here = Path(__file__).resolve().parent.parent
    figures_dir = here / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    # Apply shared theme
    apply_matplotlib_theme("paper")

    x = np.linspace(0, 2 * np.pi, 400)
    y = np.sin(2 * x) * np.exp(-0.2 * x)

    fig, ax = plt.subplots(figsize=(5, 3))
    ax.plot(x, y, label="demo signal", color=COLORS["green"])
    ax.set_xlabel("t")
    ax.set_ylabel("amplitude")
    ax.grid(True, alpha=0.25, color=COLORS["gray_light"])
    ax.legend(loc="best", frameon=False)
    fig.tight_layout()

    out_pdf = figures_dir / "fig_hello.pdf"
    out_png = figures_dir / "fig_hello.png"
    out_svg = figures_dir / "fig_hello.svg"
    fig.savefig(out_pdf, bbox_inches="tight")
    fig.savefig(out_png, dpi=300, bbox_inches="tight")
    fig.savefig(out_svg, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out_pdf}")


if __name__ == "__main__":
    main()
