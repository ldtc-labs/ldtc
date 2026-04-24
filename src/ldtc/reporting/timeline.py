"""Audit-driven verification timelines.

This module produces the headline figure for an LDTC run: a stacked
timeline of normalized `𝓛` traces and `M (dB)`, with `Ω` shading and
audit-event tick marks layered on top. All inputs come from the
[`guardrails.audit`][ldtc.guardrails.audit] JSONL log; an optional
sidecar CSV may provide *normalized* `𝓛` values directly. Raw LREG
values are never read or rendered.

Two entry points exist:

- [`render_verification_timeline`][ldtc.reporting.timeline.render_verification_timeline]
  is the legacy audit-event-density plot, kept for backwards
  compatibility.
- [`render_paper_timeline`][ldtc.reporting.timeline.render_paper_timeline]
  is the paper-style figure: log `𝓛`, `M (dB)`, `Ω` spans, audit ticks.

The figure colors and DPI come from
[`apply_matplotlib_theme`][ldtc.reporting.style.apply_matplotlib_theme]
and the shared `COLORS` palette in
[`ldtc.reporting.style`][ldtc.reporting.style].

See Also:
    `paper/main.tex`: Reporting & Figures.
"""

from __future__ import annotations

import json
import os
from typing import Dict, List, Optional, Tuple

import matplotlib.pyplot as plt

from .style import COLORS, apply_matplotlib_theme


def _read_audit(path: str) -> List[dict]:
    """Read a JSONL audit file, skipping malformed lines.

    Args:
        path: Path to the audit JSONL file.

    Returns:
        List of parsed records. A missing file yields an empty list;
        malformed lines are silently skipped so a partially corrupted
        log still produces a useful timeline.
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
                continue
    return out


def render_verification_timeline(
    audit_path: str,
    figure_path: str,
    show: bool = False,
) -> Tuple[int, int]:
    """Render a simple audit-density timeline (legacy).

    Plots audit events per second as a step function. Useful as a quick
    sanity check for audit liveness; production runs should prefer
    [`render_paper_timeline`][ldtc.reporting.timeline.render_paper_timeline].

    Args:
        audit_path: Path to the JSONL audit log.
        figure_path: Output path for the PNG figure.
        show: If `True`, display the figure interactively after saving.

    Returns:
        Tuple `(number_of_records, number_of_buckets_plotted)`.

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
    """Extract per-window time, `M (dB)`, `Ω` spans, and audit tick times.

    Walks the JSONL audit for `window_measured` records (each records a
    single `M`), `omega_<name>_start` / `omega_<name>_stop` event pairs
    (which become shaded `Ω` spans), and the events listed in
    `include_tick_events` (rendered as a thin tick rug).

    Args:
        audit_path: Path to the JSONL audit log.
        include_tick_events: Optional set of event names to render as
            ticks. Defaults to `{"partition_flip", "run_invalidated",
            "refusal_event"}`.

    Returns:
        Tuple `(times_s, m_db, omega_spans, tick_times_s)` where each
        list is in seconds relative to the first record.
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
            try:
                m = float(det.get("M", 0.0))
                t_series.append(t)
                m_db_series.append(m)
            except Exception:
                pass
        if ev.endswith("_start") and ev.startswith("omega_"):
            pending_omega[ev] = t
        elif ev.endswith("_stop") and ev.startswith("omega_"):
            base = ev.replace("_stop", "_start")
            t0 = pending_omega.pop(base, None)
            if t0 is not None:
                omega_spans.append((t0, t, ev))
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
    """Render a paper-style timeline of `𝓛` traces and `M (dB)`.

    Reads the audit log for per-window `M`, `Ω` spans, and tick events,
    optionally augmenting with a sidecar CSV of normalized `𝓛` traces.
    Without a sidecar, normalized `𝓛` is derived from `M` alone so the
    figure never depends on raw LREG values.

    Args:
        audit_path: JSONL audit log emitted by an LDTC run.
        out_base_path: Output path prefix; `.png` and `.svg` are
            appended.
        sidecar_csv: Optional CSV file with columns `time_s,L_loop,L_ex`
            (normalized).
        show: If `True`, display the figure interactively after saving.
        min_tick_spacing_s: Minimum spacing between audit tick marks (s)
            to avoid clutter.
        use_log_L: Plot `𝓛` on a log scale.
        footer_profile: Optional profile badge text (`"R0"` / `"R*"`).
            Inferred from the audit `run_header` when omitted.
        footer_audit_head: Optional last-hash value for audit
            provenance. Inferred from the last record when omitted.

    Returns:
        Dict with keys `"png"` and `"svg"` pointing to the saved figure
        paths.

    Raises:
        FileNotFoundError: If per-window `M` data are absent in the
            audit log (no `window_measured` events).
    """
    t_series, m_db_series, omega_spans, tick_times = _parse_audit_for_timeseries(audit_path)
    if not t_series or not m_db_series:
        raise FileNotFoundError("No per-window M data found in audit; ensure 'window_measured' events are present.")

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

    if not l_time:
        l_time = t_series
        l_ex = [1.0 for _ in m_db_series]
        l_loop = [10.0 ** (m / 10.0) for m in m_db_series]

    apply_matplotlib_theme("paper")

    fig, ax_l = plt.subplots(figsize=(7.0, 3.2))
    ax_m = ax_l.twinx()

    ax_l.plot(l_time, l_loop, label="L_loop (norm)", color=COLORS["green"], linewidth=1.8)
    ax_l.plot(l_time, l_ex, label="L_exchange (norm)", color=COLORS["gray"], linewidth=1.8)
    if use_log_L:
        ax_l.set_yscale("log")
    ax_l.set_xlabel("Time (s)")
    ax_l.set_ylabel("L (a.u.)")

    ax_m.plot(
        t_series,
        m_db_series,
        label="M (dB)",
        color=COLORS["yellow"],
        linewidth=1.6,
        alpha=0.9,
    )
    ax_m.set_ylabel("M (dB)")

    for idx, (t0, t1, ev) in enumerate(omega_spans):
        ax_l.axvspan(
            t0,
            t1,
            color=COLORS["gray_light"],
            alpha=0.35,
            label="Ω" if idx == 0 else None,
        )

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

    handles_l, labels_l = ax_l.get_legend_handles_labels()
    handles_m, labels_m = ax_m.get_legend_handles_labels()
    ax_l.legend(handles_l + handles_m, labels_l + labels_m, loc="upper right", frameon=False)

    try:
        m_min, m_max = min(m_db_series), max(m_db_series)
        lo = 0.0 if m_min >= 0 else m_min - 2.0
        hi = 120.0 if m_max <= 120.0 else m_max + 5.0
        ax_m.set_ylim(lo, hi)
    except Exception:
        pass

    try:
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
            if footer_audit_head is None and recs:
                footer_audit_head = str(recs[-1].get("hash", ""))
        if footer_profile or footer_audit_head:
            head_short = (footer_audit_head or "")[:12]
            footer_txt = f"Profile: {footer_profile or ''}    Audit head: {head_short}"
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
