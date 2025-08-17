from __future__ import annotations

from typing import Dict, Any

import matplotlib as mpl

try:
    from graphviz import Digraph
except Exception:  # pragma: no cover - optional at import site
    Digraph = None


# Unified, colorblind-aware palette (anchored on existing manuscript colors)
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
    """
    Apply a consistent Matplotlib style suitable for arXiv CS papers.

    - Sans-serif fonts (Helvetica fallback chain), consistent label sizes
    - Vector-friendly outputs (Type 42 fonts for PDF/PS; real text in SVG)
    - No top/right spines; tight layout handled by callers
    """
    mpl.rcParams.update(
        {
            # Fonts
            "font.family": "sans-serif",
            "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
            "text.usetex": False,
            "mathtext.fontset": "dejavusans",
            # Axes and spines
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": False,
            "axes.labelsize": 10,
            "axes.titlesize": 12,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "legend.fontsize": 9,
            # DPI and vector font embedding
            "figure.dpi": 150,
            "savefig.dpi": 300,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",  # keep text as text
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


def apply_graphviz_theme(
    dot: Any, rankdir: str = "LR", overrides: Dict[str, Dict[str, str]] | None = None
) -> None:
    """
    Apply consistent Graphviz attributes to a Digraph.
    """
    defaults = _graph_defaults(rankdir=rankdir)
    if overrides:
        # Shallow merge
        for k, v in overrides.items():
            defaults.setdefault(k, {}).update(v)
    g = defaults["graph"]
    n = defaults["node"]
    e = defaults["edge"]
    dot.attr(**g)
    dot.attr("node", **n)
    dot.attr("edge", **e)


def new_graph(name: str, rankdir: str = "LR", engine: str = "dot") -> Any:
    """
    Create a Digraph preconfigured with this project's theme.
    """
    if Digraph is None:
        raise RuntimeError("graphviz is required to build themed graphs")
    d = Digraph(name, engine=engine)
    apply_graphviz_theme(d, rankdir=rankdir)
    return d
