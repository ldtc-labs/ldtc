#!/usr/bin/env python3
"""Generate Closed loop vs exchange causal structure (numberless names).

Creates Graphviz diagrams for the C/Ex causal structure and writes
``paper/figures/fig_loop_exchange.{pdf,png,svg}``.
"""
from pathlib import Path
from ldtc.reporting.style import COLORS, apply_graphviz_theme, new_graph


def main() -> None:
    here = Path(__file__).resolve().parent.parent
    figures_dir = here / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    green_edge = COLORS["green"]
    yellow_fill = COLORS["yellow_light"]
    yellow_edge = COLORS["yellow"]
    gray_fill = COLORS["gray_light"]
    gray_edge = COLORS["gray"]

    dot = new_graph("fig_loop_exchange", rankdir="LR", engine="dot")
    apply_graphviz_theme(dot, rankdir="LR")

    with dot.subgraph(name="cluster_loop") as c:
        c.attr(label="<\n<B>Closed Self-Maintaining Loop (L<SUB>loop</SUB>)</B>\n>")
        c.attr(
            color=yellow_edge, penwidth="2.0", style="rounded", fillcolor=yellow_fill
        )
        c.attr("graph", style="filled")
        c.attr(labelloc="t", labeljust="c", margin="16")
        c.attr(rank="same")
        # Core loop nodes (solid filled circles)
        for n in ["C1", "C2", "C3", "C4"]:
            c.node(
                n,
                label=n,
                shape="circle",
                style="filled",
                color=green_edge,
                fillcolor=green_edge,
                fontcolor="#ffffff",
                width="0.6",
                fixedsize="true",
                penwidth="2.0",
            )

    # Arrange loop in a cycle by ranking and invisible helpers
    dot.edge("C1", "C2", color=green_edge, penwidth="3.6")
    dot.edge("C2", "C3", color=green_edge, penwidth="3.6")
    dot.edge("C3", "C4", color=green_edge, penwidth="3.6")
    dot.edge("C4", "C1", color=green_edge, penwidth="3.6")

    # Exchange nodes (hollow style via light fill and stroke)
    dot.node(
        "Sensor",
        label="Sensor",
        shape="circle",
        style="filled",
        color=gray_edge,
        fillcolor=gray_fill,
        penwidth="2.0",
        width="0.55",
        fixedsize="true",
    )
    dot.node(
        "Actuator",
        label="Actuator",
        shape="circle",
        style="filled",
        color=gray_edge,
        fillcolor=gray_fill,
        penwidth="2.0",
        width="0.55",
        fixedsize="true",
    )
    dot.node(
        "Comm",
        label="I/O Port",
        shape="circle",
        style="filled",
        color=gray_edge,
        fillcolor=gray_fill,
        penwidth="2.0",
        width="0.55",
        fixedsize="true",
    )

    # Thin dashed exchange edges
    dot.edge("Sensor", "C2", color=gray_edge, penwidth="2.0", style="dashed")
    dot.edge("C4", "Actuator", color=gray_edge, penwidth="2.0", style="dashed")
    dot.edge(
        "Comm",
        "C3",
        color=gray_edge,
        penwidth="2.0",
        dir="both",
        style="dashed",
    )

    stem = "fig_loop_exchange"
    dot.render(filename=stem, directory=str(figures_dir), format="pdf", cleanup=True)
    dot.render(filename=stem, directory=str(figures_dir), format="png", cleanup=True)
    dot.render(filename=stem, directory=str(figures_dir), format="svg", cleanup=True)


if __name__ == "__main__":
    main()
