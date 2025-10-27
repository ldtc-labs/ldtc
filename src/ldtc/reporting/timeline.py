"""Reporting: Timeline rendering.

Parses an audit log to render paper-style timelines of normalized L traces and
M(dB) with Ω shading and audit tick marks.

See Also:
    paper/main.tex — Reporting & Figures.
"""

from __future__ import annotations

import json
import os
from typing import Dict, List, Tuple, Optional

import matplotlib.pyplot as plt
from .style import apply_matplotlib_theme, COLORS


def _read_audit(path: str) -> List[dict]:
    """Read a JSONL audit file, skipping malformed lines.

    Args:
        path: Path to the audit JSONL file.

    Returns:
        List of parsed records.
    """
    out: List[dict] = []
    if not os.path.exists(path):
        return out
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                # Skip malformed lines
                continue
    return out


def render_verification_timeline(
    audit_path: str,
    figure_path: str,
    show: bool = False,
) -> Tuple[int, int]:
    """Render a simple audit-density timeline (legacy).

    Args:
        audit_path: Path to audit log.
        figure_path: Output path for the PNG figure.
        show: Display the figure interactively.

    Returns:
        Tuple of (number_of_records, number_of_buckets_plotted).

    Raises:
        FileNotFoundError: If the audit file has no records.
    """
    recs = _read_audit(audit_path)
    if not recs:
        raise FileNotFoundError(f"No audit records at {audit_path}")
    ts0 = recs[0]["ts"]
    bucket: Dict[int, int] = {}
    for r in recs:
        t = int(r["ts"] - ts0)
        bucket[t] = bucket.get(t, 0) + 1
    bx = sorted(bucket.keys())
    by = [bucket[t] for t in bx]
    plt.figure()
    plt.step(bx, by, where="post")
    plt.xlabel("Time (s)")
    plt.ylabel("Audit events / s")
    plt.title("Verification timeline (audit density)")
    plt.tight_layout()
    plt.savefig(figure_path)
    if show:
        plt.show()
    return len(recs), len(bx)


def _parse_audit_for_timeseries(
    audit_path: str,
    include_tick_events: Optional[set[str]] = None,
) -> Tuple[List[float], List[float], List[Tuple[float, float, str]], List[float]]:
    """Extract per-window time, M(dB), Ω spans, and audit tick times.

    Parses the JSONL audit for 'window_measured' records, omega window markers,
    and notable tick events to plot a paper-style timeline.

    Args:
        audit_path: Path to the JSONL audit log.
        include_tick_events: Optional set of event names to render as ticks.

    Returns:
        Tuple of lists: times (s), M(dB), list of Ω spans (t0, t1, label), and
        tick times (s).
    """
    recs = _read_audit(audit_path)
    if not recs:
        return [], [], [], []
    ts0 = recs[0]["ts"]
    t_series: List[float] = []
    m_db_series: List[float] = []
    omega_spans: List[Tuple[float, float, str]] = []
    tick_times: List[float] = []

    pending_omega: Dict[str, float] = {}
    include_tick_events = include_tick_events or {
        "partition_flip",
        "run_invalidated",
        "refusal_event",
    }
    for r in recs:
        t = float(r["ts"] - ts0)
        ev = r.get("event", "")
        det = r.get("details", {}) or {}
        if ev == "window_measured":
            # Per-window M(dB)
            try:
                m = float(det.get("M", 0.0))
                t_series.append(t)
                m_db_series.append(m)
            except Exception:
                pass
        # Ω span detection
        if ev.endswith("_start") and ev.startswith("omega_"):
            pending_omega[ev] = t
        elif ev.endswith("_stop") and ev.startswith("omega_"):
            # Match by prefix up to last underscore
            base = ev.replace("_stop", "_start")
            t0 = pending_omega.pop(base, None)
            if t0 is not None:
                omega_spans.append((t0, t, ev))
        # Tick-worthy audit events
        if ev in include_tick_events:
            tick_times.append(t)
    return t_series, m_db_series, omega_spans, tick_times


def render_paper_timeline(
    audit_path: str,
    out_base_path: str,
    sidecar_csv: Optional[str] = None,
    show: bool = False,
    min_tick_spacing_s: float = 0.75,
    use_log_L: bool = True,
    footer_profile: Optional[str] = None,
    footer_audit_head: Optional[str] = None,
) -> Dict[str, str]:
    """Render a paper-style timeline of L traces and M(dB).

    Args:
        audit_path: JSONL audit log emitted by runs.
        out_base_path: Output path prefix; '.png' and '.svg' are appended.
        sidecar_csv: Optional CSV file with columns time_s,L_loop,L_ex,M_db.
        show: Display the figure interactively.
        min_tick_spacing_s: Minimum spacing between audit tick marks (s).
        use_log_L: Plot L on a log scale.
        footer_profile: Optional profile badge text (R0/R*).
        footer_audit_head: Optional last-hash value for audit provenance.

    Returns:
        Dict with keys 'png' and 'svg' pointing to the saved figure paths.

    Raises:
        FileNotFoundError: If per-window M data are absent in the audit.
    """
    # Parse audit for M(dB), Ω spans, and tick times
    t_series, m_db_series, omega_spans, tick_times = _parse_audit_for_timeseries(
        audit_path
    )
    if not t_series or not m_db_series:
        raise FileNotFoundError(
            "No per-window M data found in audit; ensure 'window_measured' events are present."
        )

    # Optional: load sidecar CSV with true L traces
    l_time: List[float] = []
    l_loop: List[float] = []
    l_ex: List[float] = []
    if sidecar_csv and os.path.exists(sidecar_csv):
        import csv

        with open(sidecar_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    l_time.append(float(row.get("time_s", row.get("t", "0"))))
                    l_loop.append(float(row["L_loop"]))
                    l_ex.append(float(row["L_ex"]))
                except Exception:
                    continue

    # If no sidecar, derive normalized L traces from M only (no raw LREG exposure)
    if not l_time:
        l_time = t_series
        # Normalize so that L_ex is 1.0 and L_loop follows M ratio
        l_ex = [1.0 for _ in m_db_series]
        l_loop = [10.0 ** (m / 10.0) for m in m_db_series]

    # Apply unified theme for arXiv-ready figures
    apply_matplotlib_theme("paper")

    fig, ax_l = plt.subplots(figsize=(7.0, 3.2))
    ax_m = ax_l.twinx()

    # Plot L traces (primary axis)
    ax_l.plot(
        l_time, l_loop, label="L_loop (norm)", color=COLORS["green"], linewidth=1.8
    )
    ax_l.plot(
        l_time, l_ex, label="L_exchange (norm)", color=COLORS["gray"], linewidth=1.8
    )
    if use_log_L:
        ax_l.set_yscale("log")
    ax_l.set_xlabel("Time (s)")
    ax_l.set_ylabel("L (a.u.)")

    # Plot M(dB) (secondary axis)
    ax_m.plot(
        t_series,
        m_db_series,
        label="M (dB)",
        color=COLORS["yellow"],
        linewidth=1.6,
        alpha=0.9,
    )
    ax_m.set_ylabel("M (dB)")

    # Ω shading
    for idx, (t0, t1, ev) in enumerate(omega_spans):
        ax_l.axvspan(
            t0,
            t1,
            color=COLORS["gray_light"],
            alpha=0.35,
            label="Ω" if idx == 0 else None,
        )

    # Audit ticks (thinned rug at top of axis)
    if tick_times:
        thinned: List[float] = []
        for tt in sorted(tick_times):
            if not thinned or (tt - thinned[-1]) >= max(0.0, float(min_tick_spacing_s)):
                thinned.append(tt)
        ax_l.vlines(
            thinned,
            [0.96] * len(thinned),
            [1.0] * len(thinned),
            transform=ax_l.get_xaxis_transform(),
            colors=COLORS["gray"],
            linestyles=(0, (2, 2)),
            linewidth=0.8,
            alpha=0.7,
        )

    # Legend: combine handles from both axes
    handles_l, labels_l = ax_l.get_legend_handles_labels()
    handles_m, labels_m = ax_m.get_legend_handles_labels()
    ax_l.legend(
        handles_l + handles_m, labels_l + labels_m, loc="upper right", frameon=False
    )

    # Keep M axis within a sensible range if possible
    try:
        m_min, m_max = min(m_db_series), max(m_db_series)
        lo = 0.0 if m_min >= 0 else m_min - 2.0
        hi = 120.0 if m_max <= 120.0 else m_max + 5.0
        ax_m.set_ylim(lo, hi)
    except Exception:
        pass

    # Footer with profile badge and audit hash head (provenance)
    try:
        # If not explicitly provided, try to infer from audit header in this segment
        if footer_profile is None or footer_audit_head is None:
            recs = _read_audit(audit_path)
            prof = None
            for r in recs:
                if r.get("event") == "run_header":
                    d = r.get("details", {}) or {}
                    pid = int(d.get("profile_id", 0))
                    prof = "R*" if pid == 1 else "R0"
                    break
            footer_profile = footer_profile or (prof or "R0")
            # Use the last record's hash as a best-effort head within this segment
            if footer_audit_head is None and recs:
                footer_audit_head = str(recs[-1].get("hash", ""))
        # Compose footer string
        if footer_profile or footer_audit_head:
            head_short = (footer_audit_head or "")[:12]
            footer_txt = f"Profile: {footer_profile or ''}    Audit head: {head_short}"
            # Add extra bottom margin for footer text
            fig.subplots_adjust(bottom=0.22)
            fig.text(
                0.01,
                0.02,
                footer_txt,
                ha="left",
                va="bottom",
                fontsize=8,
                color="#444444",
            )
    except Exception:
        # Footer is best-effort; ignore failures
        pass

    fig.tight_layout()
    out_png = f"{out_base_path}.png"
    out_svg = f"{out_base_path}.svg"
    fig.savefig(out_png)
    fig.savefig(out_svg)
    if show:
        plt.show()
    plt.close(fig)
    return {"png": out_png, "svg": out_svg}
