"""Guardrails: Smell-tests and invalidation heuristics.

Includes CI width guards, partition flip-rate checks, Δt jitter thresholds,
exogenous subsidy red flags, and audit-chain integrity checks. Used by the CLI
to determine when to invalidate a run by assay.

See Also:
    paper/main.tex — Smell-tests & invalidation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple
import json
import os


@dataclass
class SmellConfig:
    """Configuration thresholds for smell-tests and guards.

    Attributes:
        max_dt_changes_per_hour: Δt edits allowed per hour.
        max_partition_flips_per_hour: Partition flips allowed per hour.
        max_ci_halfwidth: Absolute CI half-width limit.
        forbid_partition_flip_during_omega: Freeze partition during Ω.
        ci_lookback_windows: Number of windows used for CI history checks.
        ci_inflate_factor: Relative inflation vs baseline median allowed.
        jitter_p95_rel_max: Max p95(|jitter|)/dt before invalidation.
        io_suspicious_threshold: I/O threshold considered suspicious.
        min_M_rise_db: Minimum M rise to flag subsidy.
        M_rise_lookback: Look-back windows for subsidy check.
        min_harvest_for_soc_gain: Minimum H considered non-zero for SoC gains.
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
        ci: Tuple of (lo, hi) bounds.

    Returns:
        Half-width value; very large if inputs are NaN/None.
    """
    lo, hi = ci
    if any(map(lambda v: v is None or v != v, (lo, hi))):  # NaN check
        return 1e9
    return 0.5 * abs(hi - lo)


def invalid_by_ci(
    ci_loop: Tuple[float, float], ci_ex: Tuple[float, float], cfg: SmellConfig
) -> bool:
    """Check absolute CI half-width limits.

    Args:
        ci_loop: CI for loop influence.
        ci_ex: CI for exchange influence.
        cfg: Threshold configuration.

    Returns:
        True if either half-width exceeds the configured maximum.
    """
    return (
        ci_halfwidth(ci_loop) > cfg.max_ci_halfwidth
        or ci_halfwidth(ci_ex) > cfg.max_ci_halfwidth
    )


def flips_per_hour(flips: int, elapsed_sec: float) -> float:
    """Compute flip rate per hour.

    Args:
        flips: Number of flips observed.
        elapsed_sec: Elapsed time in seconds.

    Returns:
        Flip rate in events per hour.
    """
    if elapsed_sec <= 0:
        return float("inf") if flips > 0 else 0.0
    return 3600.0 * (float(flips) / float(elapsed_sec))


def invalid_by_partition_flips(
    flips: int, elapsed_sec: float, cfg: SmellConfig
) -> bool:
    """Check whether partition flip rate exceeds the configured limit.

    Args:
        flips: Number of flips observed.
        elapsed_sec: Elapsed time in seconds.
        cfg: Threshold configuration.

    Returns:
        True if flips/hour exceeds ``cfg.max_partition_flips_per_hour``.
    """
    return flips_per_hour(flips, elapsed_sec) > cfg.max_partition_flips_per_hour


def invalid_flip_during_omega(
    flips_before: int, flips_after: int, cfg: SmellConfig
) -> bool:
    """Check for partition changes during a frozen Ω window.

    Args:
        flips_before: Flip count before Ω.
        flips_after: Flip count after Ω.
        cfg: Threshold configuration.

    Returns:
        True if any flip occurred during Ω and flips are forbidden.
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

    Invalid if either median half-width over the last N windows exceeds the
    absolute limit, or if baseline medians are provided and inflated by the
    configured factor.
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

    Args:
        audit_path: Path to audit JSONL file.

    Returns:
        True if any record details contain raw LREG keys.
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
    """Heuristics for detecting exogenous subsidy conditions.

    Flags when M is rising while I/O is high and increasing, or when SoC is
    rising while harvest is ~0 over a look-back window.
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
        if (
            (M_rise >= cfg.min_M_rise_db)
            and (recent_io[-1] >= cfg.io_suspicious_threshold)
            and (io_rise > 0)
        ):
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

    Args:
        audit_path: Path to audit JSONL file.

    Returns:
        True if the chain is broken; otherwise False.
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
