#!/usr/bin/env python3
"""Generate exploded adaptive boundary (numberless names).

Creates Graphviz diagrams for an exploded view of the adaptive boundary and
writes ``paper/figures/fig_adaptive_boundary.{pdf,png,svg}``.
"""
from pathlib import Path
from ldtc.reporting.style import COLORS, apply_graphviz_theme, new_graph


def main() -> None:
    here = Path(__file__).resolve().parent.parent
    figures_dir = here / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    yellow_fill = COLORS["yellow_light"]
    yellow_edge = COLORS["yellow"]
    green_fill = COLORS["green_light"]
    green_edge = COLORS["green"]

    dot = new_graph("fig_adaptive_boundary", rankdir="TB", engine="dot")
    apply_graphviz_theme(dot, rankdir="TB")

    dot.node(
        "Outer",
        label="Outer Layer\nSelf-Healing Polyurethane",
        shape="box",
        style="rounded,filled",
        color=yellow_edge,
        fillcolor=yellow_fill,
        penwidth="2.0",
    )
    dot.node(
        "Middle",
        label="Middle Layer\nIon-Selective Hydrogel",
        shape="box",
        style="rounded,filled",
        color=yellow_edge,
        fillcolor=yellow_fill,
        penwidth="2.0",
    )
    dot.node(
        "Inner",
        label="Inner Layer\nConductive Graphene Mesh",
        shape="box",
        style="rounded,filled",
        color=yellow_edge,
        fillcolor=yellow_fill,
        penwidth="2.0",
    )

    dot.node(
        "Fibers",
        label="Embedded Piezo-Fibers\n(Strain sensing and repair trigger)",
        shape="box",
        style="rounded,filled",
        color=green_edge,
        fillcolor=green_fill,
        penwidth="2.0",
    )
    dot.node(
        "Pores",
        label="Electrostatically Gated Nanopores\n(Controlled I/O flux)",
        shape="box",
        style="rounded,filled",
        color=green_edge,
        fillcolor=green_fill,
        penwidth="2.0",
    )

    # Vertical stack for layers
    dot.edge("Outer", "Middle", color=yellow_edge, penwidth="2.0")
    dot.edge("Middle", "Inner", color=yellow_edge, penwidth="2.0")

    # Align Fibers - Middle - Pores on the same rank, with Fibers left and Pores right
    with dot.subgraph() as s:
        s.attr(rank="same")
        s.edge("Fibers", "Middle", color=green_edge, penwidth="2.0")
        s.edge("Pores", "Middle", color=green_edge, penwidth="2.0")
        # Invisible edges to hint ordering Fibers - Middle - Pores
        s.edge("Fibers", "Middle", style="invis", weight="100")
        s.edge("Middle", "Pores", style="invis", weight="100")

    stem = "fig_adaptive_boundary"
    dot.render(filename=stem, directory=str(figures_dir), format="pdf", cleanup=True)
    dot.render(filename=stem, directory=str(figures_dir), format="png", cleanup=True)
    dot.render(filename=stem, directory=str(figures_dir), format="svg", cleanup=True)


if __name__ == "__main__":
    main()
