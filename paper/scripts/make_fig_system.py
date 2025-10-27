#!/usr/bin/env python3
"""Generate system blocks and interconnections (numberless names).

Creates Graphviz diagrams for the high-level system and writes
``paper/figures/fig_system.{pdf,png,svg}``.
"""
from pathlib import Path
from ldtc.reporting.style import COLORS, apply_graphviz_theme, new_graph


def main() -> None:
    here = Path(__file__).resolve().parent.parent
    figures_dir = here / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    blue_fill = COLORS["blue_light"]
    blue_edge = COLORS["blue"]
    green_fill = COLORS["green_light"]
    green_edge = COLORS["green"]
    yellow_fill = COLORS["yellow_light"]
    yellow_edge = COLORS["yellow"]
    gray_fill = COLORS["gray_light"]
    gray_edge = COLORS["gray"]

    arrow_energy = blue_edge
    arrow_control = green_edge
    arrow_gated = gray_edge

    dot = new_graph("fig_system", rankdir="LR", engine="dot")
    # Override defaults for this figure (labels on edges are fine)
    apply_graphviz_theme(
        dot,
        rankdir="LR",
        overrides={
            "edge": {"color": gray_edge, "penwidth": "2.0"},
        },
    )

    dot.node(
        "EAM",
        label="<\n<B>Energetic-Autonomy Module</B><BR/><BR/>- On-board Reservoirs<BR/>- Load-Shedding Switches\n>",
        shape="box",
        style="rounded,filled",
        color=blue_edge,
        fillcolor=blue_fill,
        penwidth="2.0",
    )
    dot.node(
        "SRCH",
        label="<\n<B>Self-Referential<BR/>Control Hierarchy</B>\n>",
        shape="box",
        style="rounded,filled",
        color=green_edge,
        fillcolor=green_fill,
        penwidth="2.0",
    )
    dot.node(
        "AEB",
        label="<\n<B>Adaptive Encapsulation<BR/>Boundary</B>\n>",
        shape="box",
        style="rounded,filled",
        color=yellow_edge,
        fillcolor=yellow_fill,
        penwidth="2.0",
    )
    dot.node(
        "TM",
        label="<\n<B>Task Modules</B><BR/>(Peripheral)\n>",
        shape="box",
        style="rounded,filled",
        color=gray_edge,
        fillcolor=gray_fill,
        penwidth="2.0",
    )

    # Align SRCH and TM roughly on the same row
    with dot.subgraph() as s:
        s.attr(rank="same")
        s.node("SRCH")
        s.node("TM")

    # Bidirectional edges
    dot.edge(
        "EAM",
        "SRCH",
        label="Bidirectional Energy and Info",
        color=arrow_energy,
        dir="both",
        arrowhead="normal",
        arrowtail="normal",
        penwidth="2.2",
    )
    dot.edge(
        "EAM",
        "AEB",
        label="Bidirectional Energy and Info",
        color=arrow_energy,
        dir="both",
        arrowhead="normal",
        arrowtail="normal",
        penwidth="2.2",
    )
    dot.edge(
        "SRCH",
        "AEB",
        label="Bidirectional Control and Info",
        color=arrow_control,
        dir="both",
        arrowhead="normal",
        arrowtail="normal",
        penwidth="2.2",
    )
    dot.edge(
        "SRCH",
        "TM",
        label="Gated Control & Info",
        color=arrow_gated,
        dir="both",
        arrowhead="normal",
        arrowtail="normal",
        penwidth="2.0",
        style="dashed",
    )

    stem = "fig_system"
    dot.render(filename=stem, directory=str(figures_dir), format="pdf", cleanup=True)
    dot.render(filename=stem, directory=str(figures_dir), format="png", cleanup=True)
    dot.render(filename=stem, directory=str(figures_dir), format="svg", cleanup=True)


if __name__ == "__main__":
    main()
