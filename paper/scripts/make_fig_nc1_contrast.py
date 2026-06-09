#!/usr/bin/env python3
"""Generate the empirical NC1 contrast figure.

Renders the per-seed median loop dominance ``M`` (dB) for the positive control
and the negative controls into
``paper/figures/fig_nc1_contrast.{pdf,png,svg}``.

Built from the canonical multi-seed study
(``artifacts/study/study_results.json``). On a fresh checkout or in CI, where
the study has not been run, the committed
``paper/figures/fig_nc1_contrast.pdf`` (produced from that study) is used
as-is, so the paper always compiles.

See Also:
    paper/main.tex: Results (NC1 contrast).
"""

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import study  # noqa: E402
import study_figures  # noqa: E402


def main() -> None:
    figures_dir = REPO_ROOT / "paper" / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    canonical_dir = REPO_ROOT / "artifacts" / "study"
    if not (canonical_dir / "study_results.json").exists():
        # Fresh checkout / CI: there is no study to regenerate from. The
        # committed PDF (built from the canonical multi-seed study) is used
        # as-is so the paper still compiles.
        print("No canonical study found; keeping committed fig_nc1_contrast.pdf")
        return

    nc1 = ["positive", "neg_controller_disabled", "neg_permanent_ex_flood"]
    seeds = [int(os.environ.get("LDTC_FIG_SEED_BASE", "71000")) + i for i in range(3)]
    data = study.data_for_paper(
        canonical_dir=str(canonical_dir),
        fallback_dir=str(REPO_ROOT / "artifacts" / "paper_figs" / "nc1_contrast"),
        seeds=seeds,
        scenario_names=nc1,
    )
    out = study_figures.fig_nc1_contrast(data, str(figures_dir), stem="fig_nc1_contrast")
    if out:
        print(f"Wrote {os.path.splitext(out)[0]}.pdf")
    else:
        print("No NC1 runs available; keeping committed fig_nc1_contrast.pdf")


if __name__ == "__main__":
    main()
