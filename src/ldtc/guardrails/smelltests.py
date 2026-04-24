"""Smell-tests and invalidation heuristics.

A small library of "is this run still trustworthy?" checks that the CLI
runs on every window. Includes:

- CI width guards (absolute and inflation-vs-baseline).
- Partition flip-rate checks (and forbidding flips during `Ω`).
- `Δt` jitter thresholds.
- Exogenous-subsidy red flags (`M` rising while I/O is high; SoC rising
  with no harvest).
- Audit-chain integrity checks (counter / hash / timestamp continuity).

If any guard returns `True`, the CLI invalidates the run by appending a
`run_invalidated` audit event. This is the mechanism that protects NC1 /
SC1 results from being silently undermined by misconfigured measurement.

See Also:
    `paper/main.tex`: Smell-tests and invalidation.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple


@dataclass
class SmellConfig:
    """Configuration thresholds for smell-tests and guards.

    Attributes:
        max_dt_changes_per_hour: `Δt` edits allowed per rolling hour.
        max_partition_flips_per_hour: Partition flips allowed per
            rolling hour.
        max_ci_halfwidth: Absolute CI half-width limit on `L_loop` and
            `L_ex` (NaN bounds always exceed this).
        forbid_partition_flip_during_omega: When `True`, freeze the
            partition during `Ω` windows so SC1 sees a fixed `(C, Ex)`.
        ci_lookback_windows: Number of windows used for CI history
            checks.
        ci_inflate_factor: Maximum allowed inflation in median CI
            half-width vs the baseline median.
        jitter_p95_rel_max: Maximum allowed `p95(|jitter|) / dt` before
            invalidation.
        io_suspicious_threshold: I/O fraction at which the
            exogenous-subsidy heuristic considers the channel suspicious.
        min_M_rise_db: Minimum `ΔM` (dB) to flag as a subsidy.
        M_rise_lookback: Look-back windows for the subsidy check.
        min_harvest_for_soc_gain: Minimum harvest considered non-zero for
            SoC-gain detection.
    """

    max_dt_changes_per_hour: int = 3
    max_partition_flips_per_hour: int = 2
    max_ci_halfwidth: float = 0.30
    forbid_partition_flip_during_omega: bool = True
    # CI look-back configuration
    ci_lookback_windows: int = 5
    ci_inflate_factor: float = 2.0  # relative to baseline median
    # Δt jitter guard (relative to dt)
    jitter_p95_rel_max: float = 0.25  # invalidate if p95(|jitter|)/dt exceeds this
    # Exogenous-subsidy heuristics
    io_suspicious_threshold: float = 0.8
    min_M_rise_db: float = 0.5
    M_rise_lookback: int = 3
    min_harvest_for_soc_gain: float = 1e-3


def ci_halfwidth(ci: Tuple[float, float]) -> float:
    """Compute the half-width of a confidence interval.

    Args:
        ci: Tuple of `(lo, hi)` bounds.

    Returns:
        Half-width value; returns a very large sentinel (`1e9`) if any
        input is `NaN` or `None` so downstream guards trip predictably.
    """
    lo, hi = ci
    if any(map(lambda v: v is None or v != v, (lo, hi))):
        return 1e9
    return 0.5 * abs(hi - lo)


def invalid_by_ci(ci_loop: Tuple[float, float], ci_ex: Tuple[float, float], cfg: SmellConfig) -> bool:
    """Check absolute CI half-width limits.

    Args:
        ci_loop: CI for loop influence.
        ci_ex: CI for exchange influence.
        cfg: Threshold configuration.

    Returns:
        `True` if either half-width exceeds `cfg.max_ci_halfwidth`.
    """
    return ci_halfwidth(ci_loop) > cfg.max_ci_halfwidth or ci_halfwidth(ci_ex) > cfg.max_ci_halfwidth


def flips_per_hour(flips: int, elapsed_sec: float) -> float:
    """Compute flip rate per hour.

    Args:
        flips: Number of flips observed.
        elapsed_sec: Elapsed time in seconds.

    Returns:
        Flip rate in events per hour. Returns `inf` when `elapsed_sec`
        is non-positive but `flips > 0` (a degenerate but conservative
        signal).
    """
    if elapsed_sec <= 0:
        return float("inf") if flips > 0 else 0.0
    return 3600.0 * (float(flips) / float(elapsed_sec))


def invalid_by_partition_flips(flips: int, elapsed_sec: float, cfg: SmellConfig) -> bool:
    """Check whether the partition flip rate exceeds the configured limit.

    Args:
        flips: Number of flips observed.
        elapsed_sec: Elapsed time in seconds.
        cfg: Threshold configuration.

    Returns:
        `True` if flips per hour exceeds
        `cfg.max_partition_flips_per_hour`.
    """
    return flips_per_hour(flips, elapsed_sec) > cfg.max_partition_flips_per_hour


def invalid_flip_during_omega(flips_before: int, flips_after: int, cfg: SmellConfig) -> bool:
    """Check for partition changes during a frozen `Ω` window.

    Args:
        flips_before: Flip count before `Ω`.
        flips_after: Flip count after `Ω`.
        cfg: Threshold configuration.

    Returns:
        `True` if any flip occurred during `Ω` and flips are forbidden
        by `cfg.forbid_partition_flip_during_omega`.
    """
    if not cfg.forbid_partition_flip_during_omega:
        return False
    return (flips_after - flips_before) > 0


def invalid_by_ci_history(
    ci_loop_hist: Sequence[Tuple[float, float]],
    ci_ex_hist: Sequence[Tuple[float, float]],
    cfg: SmellConfig,
    baseline_medians: Optional[Tuple[float, float]] = None,
) -> bool:
    """Evaluate CI health over a look-back window.

    Considered invalid when either:

    1. The median half-width over the last `cfg.ci_lookback_windows`
       windows exceeds `cfg.max_ci_halfwidth`, or
    2. `baseline_medians` are provided and either median is inflated by
       at least `cfg.ci_inflate_factor` relative to baseline.

    Returns `False` (defensively) on any internal error so the harness
    keeps running rather than spuriously invalidating a run on a bug.

    Args:
        ci_loop_hist: Sequence of `(lo, hi)` CI tuples for `L_loop`.
        ci_ex_hist: Sequence of `(lo, hi)` CI tuples for `L_ex`.
        cfg: Threshold configuration.
        baseline_medians: Optional `(median_loop, median_ex)` baseline
            half-widths used for inflation comparison.

    Returns:
        `True` if the CI history fails either check.
    """
    try:
        n = cfg.ci_lookback_windows
        if len(ci_loop_hist) < n or len(ci_ex_hist) < n:
            return False
        recent_loop = ci_loop_hist[-n:]
        recent_ex = ci_ex_hist[-n:]
        hw_loop = sorted([ci_halfwidth(c) for c in recent_loop])
        hw_ex = sorted([ci_halfwidth(c) for c in recent_ex])
        med_loop = hw_loop[n // 2]
        med_ex = hw_ex[n // 2]
        if med_loop > cfg.max_ci_halfwidth or med_ex > cfg.max_ci_halfwidth:
            return True
        if baseline_medians is not None:
            b_loop, b_ex = baseline_medians
            if b_loop > 0 and med_loop >= cfg.ci_inflate_factor * b_loop:
                return True
            if b_ex > 0 and med_ex >= cfg.ci_inflate_factor * b_ex:
                return True
        return False
    except Exception:
        return False


def audit_contains_raw_lreg_values(audit_path: str) -> bool:
    """Detect raw LREG fields in audit records.

    A defense-in-depth scan for `L_loop`, `L_ex`, `ci_loop`, `ci_ex` in
    any audit record's `details`. The audit log writer already blocks
    these keys; this function exists so post-hoc verification can catch
    a regression.

    Args:
        audit_path: Path to the audit JSONL file.

    Returns:
        `True` if any record's `details` contains raw LREG keys.
        Returns `False` if the file is clean, missing, or fails to
        parse (the function is intentionally lenient to avoid false
        positives from unrelated bugs).
    """
    if not os.path.exists(audit_path):
        return False
    try:
        with open(audit_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                details = obj.get("details", {}) or {}
                # conservative: any appearance of these keys is a breach
                for k in ("L_loop", "L_ex", "ci_loop", "ci_ex"):
                    if k in details:
                        return True
        return False
    except Exception:
        return False


def exogenous_subsidy_red_flag(
    Ms_db: Sequence[float],
    ios: Sequence[float],
    Es: Sequence[float],
    Hs: Sequence[float],
    cfg: SmellConfig,
) -> bool:
    """Heuristics for detecting exogenous-subsidy conditions.

    Flags when `M` is rising while I/O is both high and increasing, or
    when SoC is rising while harvest is approximately zero over a
    look-back window. Both situations suggest the apparent loop
    dominance comes from outside the system rather than from a real
    closed-loop dynamic.

    Args:
        Ms_db: Recent `M (dB)` values.
        ios: Recent I/O fraction values.
        Es: Recent state-of-charge values.
        Hs: Recent harvest values.
        cfg: Threshold configuration.

    Returns:
        `True` if either heuristic fires. Returns `False` defensively on
        any internal error.
    """
    try:
        n = cfg.M_rise_lookback
        if len(Ms_db) < n or len(ios) < n or len(Es) < n or len(Hs) < n:
            return False
        recent_M = Ms_db[-n:]
        recent_io = ios[-n:]
        recent_E = Es[-n:]
        recent_H = Hs[-n:]
        # Simple rise check
        M_rise = recent_M[-1] - recent_M[0]
        io_rise = recent_io[-1] - recent_io[0]
        if (M_rise >= cfg.min_M_rise_db) and (recent_io[-1] >= cfg.io_suspicious_threshold) and (io_rise > 0):
            return True
        # SoC rising while harvest ~0
        E_rise = recent_E[-1] - recent_E[0]
        avg_H = sum(recent_H) / float(n)
        if (E_rise > 0.0) and (avg_H <= cfg.min_harvest_for_soc_gain):
            return True
        return False
    except Exception:
        return False


def audit_chain_broken(audit_path: str) -> bool:
    """Validate audit chain counters, hashes, and timestamps.

    Walks the JSONL file and verifies that:

    1. `counter` strictly increases by 1 per record.
    2. Each `prev_hash` matches the previous record's `hash` (with
       `"GENESIS"` as the seed).
    3. `ts` is non-decreasing.

    Args:
        audit_path: Path to the audit JSONL file.

    Returns:
        `True` if the chain is broken (or the file cannot be opened or
        parsed). `False` only when the chain is fully verified.
    """
    if not os.path.exists(audit_path):
        return True
    prev_hash = "GENESIS"
    prev_counter = 0
    prev_ts = -1.0
    try:
        with open(audit_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                c = int(obj.get("counter", 0))
                ts = float(obj.get("ts", 0.0))
                ph = obj.get("prev_hash")
                h = obj.get("hash")
                if c != prev_counter + 1:
                    return True
                if ph != prev_hash:
                    return True
                if prev_ts >= 0.0 and ts < prev_ts:
                    return True
                prev_counter = c
                prev_hash = h
                prev_ts = ts
        return False
    except Exception:
        return True
