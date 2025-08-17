#!/usr/bin/env python3
"""Generate meta-policy override state machine (numberless names).

Outputs: paper/figures/fig_meta_policy.{pdf,png,svg}
"""
from pathlib import Path

from graphviz import Digraph


def main() -> None:
    here = Path(__file__).resolve().parent.parent
    figures_dir = here / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    gray_fill = "#F2F3F4"
    gray_edge = "#7F8C8D"
    yellow_fill = "#FEF9E7"
    yellow_edge = "#D4AC0D"
    green_fill = "#D1F2EB"
    green_edge = "#138D75"
    red_fill = "#FADBD8"
    red_edge = "#C0392B"
    blue_fill = "#D6EAF8"
    blue_edge = "#2874A6"
    dot = Digraph("fig_meta_policy", engine="dot")
    dot.attr(
        rankdir="LR",
        splines="spline",
        nodesep="0.6",
        ranksep="0.9",
        margin="0.25",
        pad="0.2",
        dpi="300",
    )
    dot.attr("node", fontname="Helvetica", fontsize="10")
    dot.attr("edge", fontname="Helvetica", fontsize="10")

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
        "D",
        label="<\n<B>Command Approved</B><BR/>Execute instruction as per task module\n>",
        shape="box",
        style="rounded,filled",
        color=gray_edge,
        fillcolor=gray_fill,
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
    dot.node(
        "H",
        label="<\n<B>Return to Normal Operation</B><BR/>Re-evaluate queued commands\n>",
        shape="box",
        style="rounded,filled",
        color=gray_edge,
        fillcolor=gray_fill,
        penwidth="2.0",
    )

    dot.edge("A", "B", color=gray_edge, penwidth="2.0")
    dot.edge("B", "C", color=yellow_edge, penwidth="2.0")
    dot.edge(
        "C",
        "D",
        xlabel="No Threat\n(Survival Bit OK)",
        color=green_edge,
        penwidth="2.0",
    )
    dot.edge("D", "A", color=gray_edge, penwidth="2.0")
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
        "H",
        xlabel="Yes\n(Boundary Secure)",
        color=green_edge,
        penwidth="2.0",
    )
    dot.edge("H", "A", color=gray_edge, penwidth="2.0")

    stem = "fig_meta_policy"
    dot.render(filename=stem, directory=str(figures_dir), format="pdf", cleanup=True)
    dot.render(filename=stem, directory=str(figures_dir), format="png", cleanup=True)
    dot.render(filename=stem, directory=str(figures_dir), format="svg", cleanup=True)


if __name__ == "__main__":
    main()
