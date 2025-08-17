#!/usr/bin/env python3
"""Generate meta-policy override state machine (numberless names).

Outputs: paper/figures/fig_meta_policy.{pdf,png,svg}
"""
from pathlib import Path

from graphviz import Digraph

from ldtc.reporting.style import COLORS, apply_graphviz_theme, new_graph


def main() -> None:
    here = Path(__file__).resolve().parent.parent
    figures_dir = here / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    gray_fill = COLORS["gray_light"]
    gray_edge = COLORS["gray"]
    yellow_fill = COLORS["yellow_light"]
    yellow_edge = COLORS["yellow"]
    green_fill = COLORS["green_light"]
    green_edge = COLORS["green"]
    red_fill = COLORS["red_light"]
    red_edge = COLORS["red"]
    blue_fill = COLORS["blue_light"]
    blue_edge = COLORS["blue"]
    dot = new_graph("fig_meta_policy", rankdir="LR", engine="dot")
    apply_graphviz_theme(dot, rankdir="LR")

    dot.node(
        "A",
        label="<\n<B>Normal Operation</B><BR/>Executing task queue\n>",
        shape="box",
        style="rounded,filled",
        color=gray_edge,
        fillcolor=gray_fill,
        penwidth="2.0",
    )
    dot.node(
        "B",
        label="<\n<B>External Command Intercepted</B><BR/>via Adaptive Encapsulation Boundary\n>",
        shape="box",
        style="rounded,filled",
        color=yellow_edge,
        fillcolor=yellow_fill,
        penwidth="2.0",
    )
    dot.node(
        "C",
        label="<\n<B>Survival Threat Assessment</B><BR/>Is L<SUB>loop</SUB> &gt; L<SUB>exchange</SUB> at risk?\n>",
        shape="diamond",
        style="filled",
        color=green_edge,
        fillcolor=green_fill,
        penwidth="2.0",
    )
    dot.node(
        "E",
        label="<\n<B>Command Refused &amp; Queued</B><BR/>Trigger Non-Maskable Interrupt\n>",
        shape="box",
        style="rounded,filled",
        color=red_edge,
        fillcolor=red_fill,
        penwidth="2.0",
    )
    dot.node(
        "F",
        label="<\n<B>Autonomy Routine Initiated</B><BR/>- Suspend peripheral tasks<BR/>- Reallocate energy to boundary<BR/>- Initiate resource foraging\n>",
        shape="box",
        style="rounded,filled",
        color=blue_edge,
        fillcolor=blue_fill,
        penwidth="2.0",
    )
    dot.node(
        "G",
        label="<\n<B>Recovery Condition Check</B><BR/>Is L<SUB>loop</SUB> &gt; (L<SUB>exchange</SUB> + σ)?\n>",
        shape="diamond",
        style="filled",
        color=green_edge,
        fillcolor=green_fill,
        penwidth="2.0",
    )

    dot.body.append("{rank = same; B; G}")
    dot.body.append("{rank = same; C; E; F}")

    dot.edge("A", "B", color=gray_edge, penwidth="2.0")
    dot.edge("B", "C", color=yellow_edge, penwidth="2.0")
    dot.edge(
        "C",
        "A",
        xlabel="No Threat\n(Survival Bit OK)",
        color=green_edge,
        penwidth="2.0",
    )
    dot.edge(
        "C",
        "E",
        xlabel="Threat Detected\n(Survival Bit Flagged)",
        color=green_edge,
        penwidth="2.0",
    )
    dot.edge("E", "F", color=red_edge, penwidth="2.0")
    dot.edge("F", "G", color=blue_edge, penwidth="2.0")
    dot.edge(
        "G",
        "F",
        xlabel="No\n(Condition Not Met)",
        color=green_edge,
        penwidth="2.0",
    )
    dot.edge(
        "G",
        "A",
        xlabel="Yes\n(Boundary Secure)",
        color=green_edge,
        penwidth="2.0",
    )

    stem = "fig_meta_policy"
    dot.render(filename=stem, directory=str(figures_dir), format="pdf", cleanup=True)
    dot.render(filename=stem, directory=str(figures_dir), format="png", cleanup=True)
    dot.render(filename=stem, directory=str(figures_dir), format="svg", cleanup=True)


if __name__ == "__main__":
    main()
