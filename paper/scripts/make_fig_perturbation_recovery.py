#!/usr/bin/env python3
"""Generate the empirical perturbation-recovery (SC1) figure.

Renders the seed-aggregated loop-dominance trajectory ``M(t)`` for the SC1
perturbation battery (power sag, sustained ingress flood, and the
designed-fail control outage) into
``paper/figures/fig_perturbation_recovery.{pdf,png,svg}``.

The figure is built from the canonical multi-seed study
(``artifacts/study/study_results.json`` plus the per-run audit logs it
references). On a fresh checkout or in CI, where the study has not been run,
the committed ``paper/figures/fig_perturbation_recovery.pdf`` (produced from
that study) is used as-is, so the paper always compiles.

See Also:
    paper/main.tex: Results (perturbation-recovery).
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
        print("No canonical study found; keeping committed fig_perturbation_recovery.pdf")
        return

    sc1 = ["sc1_power_sag", "sc1_ingress_flood", "sc1_control_outage"]
    seeds = [int(os.environ.get("LDTC_FIG_SEED_BASE", "70000")) + i for i in range(3)]
    data = study.data_for_paper(
        canonical_dir=str(canonical_dir),
        fallback_dir=str(REPO_ROOT / "artifacts" / "paper_figs" / "perturbation_recovery"),
        seeds=seeds,
        scenario_names=sc1,
    )
    out = study_figures.fig_sc1_recovery(data, str(figures_dir), stem="fig_perturbation_recovery")
    if out:
        print(f"Wrote {os.path.splitext(out)[0]}.pdf")
    else:
        print("No SC1 trajectories available; keeping committed fig_perturbation_recovery.pdf")


if __name__ == "__main__":
    main()
