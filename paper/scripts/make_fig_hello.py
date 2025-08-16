#!/usr/bin/env python3
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def main() -> None:
    here = Path(__file__).resolve().parent.parent
    figures_dir = here / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    x = np.linspace(0, 2 * np.pi, 400)
    y = np.sin(2 * x) * np.exp(-0.2 * x)

    fig, ax = plt.subplots(figsize=(5, 3))
    ax.plot(x, y, label="demo signal")
    ax.set_xlabel("t")
    ax.set_ylabel("amplitude")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", frameon=False)
    fig.tight_layout()

    out_pdf = figures_dir / "fig_hello.pdf"
    fig.savefig(out_pdf)
    plt.close(fig)
    print(f"Wrote {out_pdf}")


if __name__ == "__main__":
    main()
