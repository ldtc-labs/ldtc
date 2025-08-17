#!/usr/bin/env python3
"""Generate developmental bootstrapping flow (numberless names).

Outputs: paper/figures/fig_dev_bootstrap.{pdf,png,svg}
"""
from pathlib import Path
from ldtc.reporting.style import COLORS, apply_graphviz_theme, new_graph


def main() -> None:
    here = Path(__file__).resolve().parent.parent
    figures_dir = here / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    purple_fill = COLORS["purple_light"]
    purple_edge = COLORS["purple"]

    dot = new_graph("fig_dev_bootstrap", rankdir="LR", engine="dot")
    apply_graphviz_theme(dot, rankdir="LR")

    dot.node(
        "SA",
        label="<\n<B>Seed Activation</B><BR/><I>(Stage 0)</I><BR/><BR/>Protocell hydrated;<BR/>minimal policy initialized\n>",
        shape="box",
        style="rounded,filled",
        color=purple_edge,
        fillcolor=purple_fill,
        penwidth="2.0",
    )
    dot.node(
        "EC",
        label="<\n<B>Environmental Calibration</B><BR/><I>(Stage 1)</I><BR/><BR/>Homeostat explores<BR/>actuator-sensor mappings\n>",
        shape="box",
        style="rounded,filled",
        color=purple_edge,
        fillcolor=purple_fill,
        penwidth="2.0",
    )
    dot.node(
        "HM",
        label="<\n<B>Homeostat Maturation</B><BR/><I>(Stage 1)</I><BR/><BR/>Causal loop gain factors<BR/>converge with &lt; 5% error\n>",
        shape="box",
        style="rounded,filled",
        color=purple_edge,
        fillcolor=purple_fill,
        penwidth="2.0",
    )
    dot.node(
        "BH",
        label="<\n<B>Boundary Hardening</B><BR/><I>(Stage 2)</I><BR/><BR/>Membrane thickens;<BR/>firewall keys generated\n>",
        shape="box",
        style="rounded,filled",
        color=purple_edge,
        fillcolor=purple_fill,
        penwidth="2.0",
    )
    dot.node(
        "AO",
        label="<\n<B>Autonomous Operation</B><BR/><I>(Stage 3)</I><BR/><BR/>Mature agent qualified in<BR/>gradient/obstacle arena\n>",
        shape="box",
        style="rounded,filled",
        color=purple_edge,
        fillcolor=purple_fill,
        penwidth="2.0",
    )

    dot.edge("SA", "EC", color=purple_edge, penwidth="2.0")
    dot.edge("EC", "HM", color=purple_edge, penwidth="2.0")
    dot.edge("HM", "BH", color=purple_edge, penwidth="2.0")
    dot.edge("BH", "AO", color=purple_edge, penwidth="2.0")

    stem = "fig_dev_bootstrap"
    dot.render(filename=stem, directory=str(figures_dir), format="pdf", cleanup=True)
    dot.render(filename=stem, directory=str(figures_dir), format="png", cleanup=True)
    dot.render(filename=stem, directory=str(figures_dir), format="svg", cleanup=True)


if __name__ == "__main__":
    main()
