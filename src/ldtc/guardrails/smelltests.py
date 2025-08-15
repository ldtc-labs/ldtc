from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple
import json
import os


@dataclass
class SmellConfig:
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
    lo, hi = ci
    if any(map(lambda v: v is None or v != v, (lo, hi))):  # NaN check
        return 1e9
    return 0.5 * abs(hi - lo)


def invalid_by_ci(
    ci_loop: Tuple[float, float], ci_ex: Tuple[float, float], cfg: SmellConfig
) -> bool:
    return (
        ci_halfwidth(ci_loop) > cfg.max_ci_halfwidth
        or ci_halfwidth(ci_ex) > cfg.max_ci_halfwidth
    )


def flips_per_hour(flips: int, elapsed_sec: float) -> float:
    if elapsed_sec <= 0:
        return float("inf") if flips > 0 else 0.0
    return 3600.0 * (float(flips) / float(elapsed_sec))


def invalid_by_partition_flips(
    flips: int, elapsed_sec: float, cfg: SmellConfig
) -> bool:
    return flips_per_hour(flips, elapsed_sec) > cfg.max_partition_flips_per_hour


def invalid_flip_during_omega(
    flips_before: int, flips_after: int, cfg: SmellConfig
) -> bool:
    if not cfg.forbid_partition_flip_during_omega:
        return False
    return (flips_after - flips_before) > 0


def invalid_by_ci_history(
    ci_loop_hist: Sequence[Tuple[float, float]],
    ci_ex_hist: Sequence[Tuple[float, float]],
    cfg: SmellConfig,
    baseline_medians: Optional[Tuple[float, float]] = None,
) -> bool:
    """
    Evaluate CI health over a look-back window.
    - If median relative half-width over the last N windows exceeds max_ci_halfwidth → invalid
    - If baseline medians are provided and current medians inflate ≥ factor → invalid
    ci_*_hist: list of (lo, hi) tuples
    baseline_medians: optional (median_halfwidth_loop, median_halfwidth_ex)
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
    """
    Returns True if any audit record appears to include raw LREG values or CI bounds
    (keys like L_loop, L_ex, ci_loop, ci_ex) in its details.
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
    """
    Heuristic flags for exogenous subsidy:
    - M rising over lookback while io is high/increasing toward threshold
    - E (SoC) rising while harvest H is ~0 (below min_harvest_for_soc_gain)
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
    """
    Returns True if the JSONL audit chain shows a counter gap or hash-chain break
    or non-monotonic timestamps.
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
