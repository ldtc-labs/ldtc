#!/usr/bin/env python3
"""Generate System blocks and interconnections (numberless names).

Outputs: paper/figures/fig_system.{pdf,png,svg}
"""
from pathlib import Path

from graphviz import Digraph


def main() -> None:
    here = Path(__file__).resolve().parent.parent
    figures_dir = here / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    blue_fill = "#D6EAF8"
    blue_edge = "#2874A6"
    green_fill = "#D1F2EB"
    green_edge = "#138D75"
    yellow_fill = "#FEF9E7"
    yellow_edge = "#D4AC0D"
    gray_fill = "#F2F3F4"
    gray_edge = "#7F8C8D"

    arrow_energy = blue_edge
    arrow_control = green_edge
    arrow_gated = gray_edge

    dot = Digraph("fig_system", engine="dot")
    dot.attr(
        rankdir="LR",
        splines="spline",
        nodesep="0.6",
        ranksep="0.8",
        margin="0.25",
        pad="0.2",
        dpi="300",
    )
    dot.attr("node", fontname="Helvetica", fontsize="10")
    dot.attr("edge", fontname="Helvetica", fontsize="10")

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
