"""Plot and graph styles for LDTC figures.

Provides a small, opinionated theme that the rest of
[`ldtc.reporting`][ldtc.reporting] uses to make figures consistent
across the docs site, the paper, and per-run artifact bundles. Three
helpers are exposed:

- [`apply_matplotlib_theme`][ldtc.reporting.style.apply_matplotlib_theme]
  sets fonts, axes, and DPI on the global Matplotlib `rcParams`.
- [`apply_graphviz_theme`][ldtc.reporting.style.apply_graphviz_theme]
  decorates a `Digraph` with the LDTC palette and layout defaults.
- [`new_graph`][ldtc.reporting.style.new_graph] is a convenience
  constructor that returns an already-themed `Digraph`.

The shared `COLORS` palette in this module is colorblind-aware and
anchored on the manuscript's existing colors so figures composed in
the docs match the paper.

See Also:
    `paper/main.tex`: Reporting & Figures.
"""

from __future__ import annotations

from typing import Any, Dict

import matplotlib as mpl

try:
    from graphviz import Digraph
except Exception:  # pragma: no cover - optional at import site
    Digraph = None


COLORS: Dict[str, str] = {
    "blue": "#2874A6",
    "blue_light": "#D6EAF8",
    "green": "#138D75",
    "green_light": "#D1F2EB",
    "yellow": "#D4AC0D",
    "yellow_light": "#FEF9E7",
    "gray": "#7F8C8D",
    "gray_light": "#F2F3F4",
    "purple": "#8E44AD",
    "purple_light": "#E8DAEF",
    "red": "#C0392B",
    "red_light": "#FADBD8",
}


def apply_matplotlib_theme(kind: str = "paper") -> None:
    """Apply a consistent Matplotlib style.

    Configures fonts, spine visibility, label sizes, and vector-friendly
    output settings so that figures in the docs site and the paper share
    a single visual language. The function mutates the global Matplotlib
    `rcParams`; call it once at process start.

    Args:
        kind: Optional style variant. Currently informational; only the
            default paper-style theme is implemented.
    """
    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
            "text.usetex": False,
            "mathtext.fontset": "dejavusans",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": False,
            "axes.labelsize": 10,
            "axes.titlesize": 12,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "legend.fontsize": 9,
            "figure.dpi": 150,
            "savefig.dpi": 300,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
        }
    )


def _graph_defaults(rankdir: str = "LR") -> Dict[str, Dict[str, str]]:
    return {
        "graph": {
            "rankdir": str(rankdir),
            "splines": "spline",
            "nodesep": "0.6",
            "ranksep": "0.8",
            "margin": "0.25",
            "pad": "0.2",
            "dpi": "300",
        },
        "node": {
            "fontname": "Helvetica",
            "fontsize": "10",
            "style": "rounded,filled",
            "color": COLORS["gray"],
            "fillcolor": COLORS["gray_light"],
            "penwidth": "2.0",
        },
        "edge": {
            "fontname": "Helvetica",
            "fontsize": "10",
            "color": COLORS["gray"],
            "penwidth": "2.0",
        },
    }


def apply_graphviz_theme(dot: Any, rankdir: str = "LR", overrides: Dict[str, Dict[str, str]] | None = None) -> None:
    """Apply consistent Graphviz attributes to a Digraph.

    Args:
        dot: A `graphviz.Digraph` instance.
        rankdir: Graph layout direction; either `"LR"` (left-to-right)
            or `"TB"` (top-to-bottom).
        overrides: Optional nested dict overriding default
            graph/node/edge attributes. Top-level keys must be one of
            `"graph"`, `"node"`, or `"edge"`; values are merged
            shallowly into the defaults so callers can override only the
            attributes they care about.
    """
    defaults = _graph_defaults(rankdir=rankdir)
    if overrides:
        for k, v in overrides.items():
            defaults.setdefault(k, {}).update(v)
    g = defaults["graph"]
    n = defaults["node"]
    e = defaults["edge"]
    dot.attr(**g)
    dot.attr("node", **n)
    dot.attr("edge", **e)


def new_graph(name: str, rankdir: str = "LR", engine: str = "dot") -> Any:
    """Create a themed Graphviz Digraph.

    Args:
        name: Graph name. Used by Graphviz for the rendered file's
            top-level identifier.
        rankdir: Layout direction; see
            [`apply_graphviz_theme`][ldtc.reporting.style.apply_graphviz_theme].
        engine: Graphviz engine (e.g., `"dot"`, `"neato"`).

    Returns:
        A `graphviz.Digraph` with the LDTC palette and layout defaults
        already applied.

    Raises:
        RuntimeError: If `graphviz` is not installed.
    """
    if Digraph is None:
        raise RuntimeError("graphviz is required to build themed graphs")
    d = Digraph(name, engine=engine)
    apply_graphviz_theme(d, rankdir=rankdir)
    return d
