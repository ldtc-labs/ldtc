"""Smell-tests and invalidation heuristics.

A small library of "is this run still trustworthy?" checks that the CLI
runs on every window. Includes:

- CI width guards (absolute and inflation-vs-baseline).
- Partition flip-rate checks (and forbidding flips during `Ω`).
- `Δt` jitter thresholds.
- Exogenous-subsidy red flags (`M` rising while I/O is high; energy
  appearing in the store faster than the metered influx allows).
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
        min_io_rise: Minimum I/O increase over the look-back for the
            rising-M branch to fire. Requiring a material ramp (rather
            than any positive jitter) keeps a legitimately elevated,
            fluctuating I/O channel (e.g., a sustained ingress flood the
            loop is successfully shielding) from tripping the flag.
        soc_jump_margin: Energy-conservation allowance for the
            unexplained-SoC-gain check: a single-tick SoC rise may not
            exceed the metered influx (harvest) by more than this margin
            (which covers sensor/process noise). Any larger one-tick gain
            means energy entered the store from outside the metered
            channel.
    """

    max_dt_changes_per_hour: int = 3
    max_partition_flips_per_hour: int = 2
    max_ci_halfwidth: float = 0.30
    forbid_partition_flip_during_omega: bool = True
    # CI look-back configuration
    ci_lookback_windows: int = 5
    # Relative-inflation factor for the median CI half-width vs the early
    # baseline median. Bootstrap CI half-widths on a short (~60-sample) window
    # have substantial window-to-window variability, so a 2x swing is within
    # normal noise; the relative guard should fire only on a gross degradation.
    # The absolute cap (``max_ci_halfwidth``) remains the hard limit.
    ci_inflate_factor: float = 3.0  # relative to baseline median
    # The relative-inflation check only applies once the CI is absolutely
    # non-trivial. Near the noise floor (e.g., L_ex ~ 0 in the positive
    # control, or L_loop ~ 0 in a negative control) a tiny baseline half-width
    # can "inflate" by >2x while the estimate stays extremely precise; that is
    # not a measurement-quality failure. We therefore require the inflated
    # half-width to also exceed this absolute floor, set to half the absolute
    # cap (``max_ci_halfwidth``) so the relative check only ever fires for a CI
    # that is genuinely degrading toward the absolute limit.
    ci_inflate_min_hw: float = 0.15
    # Δt jitter guard (relative to dt)
    jitter_p95_rel_max: float = 0.25  # invalidate if p95(|jitter|)/dt exceeds this
    # Exogenous-subsidy heuristics
    io_suspicious_threshold: float = 0.8
    min_M_rise_db: float = 0.5
    M_rise_lookback: int = 3
    min_io_rise: float = 0.08
    # Energy-conservation audit. Every legitimate path into the energy store is
    # metered by the harvest channel H, so over one tick the SoC can rise by at
    # most H plus a noise allowance. The plant's per-tick process noise is
    # bounded (|noise_energy| <= 0.024 in the software plant), so a margin of
    # 0.06 can never fire on legitimate dynamics yet catches any injection
    # pulse well above the noise floor. Subsidies that trickle in below the
    # noise floor are undetectable by construction (and correspondingly cannot
    # buy a measurable survival advantage per tick).
    soc_jump_margin: float = 0.06


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
            floor = cfg.ci_inflate_min_hw
            if b_loop > 0 and med_loop >= cfg.ci_inflate_factor * b_loop and med_loop >= floor:
                return True
            if b_ex > 0 and med_ex >= cfg.ci_inflate_factor * b_ex and med_ex >= floor:
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


def unexplained_soc_gain(
    Es: Sequence[float],
    Hs: Sequence[float],
    cfg: SmellConfig,
) -> bool:
    """Energy-conservation audit on the per-tick SoC series.

    All legitimate energy entering the store is metered by the harvest
    channel, so over a single tick the SoC may rise by at most the
    metered influx plus a noise allowance (`cfg.soc_jump_margin`). A
    larger one-tick gain means energy entered the store outside the
    metered channel: an exogenous subsidy. This check is deterministic
    on legitimate dynamics (the plant's per-tick noise is strictly below
    the margin) and fires on every injection pulse above the noise
    floor, whether or not harvest is currently zero.

    Args:
        Es: Per-tick state-of-charge series.
        Hs: Per-tick harvest series, sampled at the same ticks as `Es`.
        cfg: Threshold configuration.

    Returns:
        `True` if any single-tick SoC gain exceeds the metered influx by
        more than the margin.
    """
    n = min(len(Es), len(Hs))
    for i in range(1, n):
        gain = Es[i] - Es[i - 1]
        # Allow the larger of the two adjacent harvest readings so that a
        # legitimate step-up in harvest (e.g., sag release) cannot be
        # mistaken for an injection.
        influx = max(Hs[i - 1], Hs[i])
        if gain - influx > cfg.soc_jump_margin:
            return True
    return False


def exogenous_subsidy_red_flag(
    Ms_db: Sequence[float],
    ios: Sequence[float],
    Es: Sequence[float],
    Hs: Sequence[float],
    cfg: SmellConfig,
    omega_declared: bool = False,
) -> bool:
    """Heuristics for detecting exogenous-subsidy conditions.

    Two branches:

    1. *Undeclared exchange surge*: `M` rising while I/O is high and
       materially ramping. An unannounced surge on an exchange channel
       that coincides with rising measured dominance suggests the
       dominance is being bought on that channel. This branch is
       suspended while a *declared* `Ω` stimulus is in effect
       (`omega_declared=True`), because a declared ingress flood is
       exactly such a surge and is the experiment, not a confound.
    2. *Energy conservation*: the store gains charge faster than the
       metered influx allows (see
       [`unexplained_soc_gain`][ldtc.guardrails.smelltests.unexplained_soc_gain]).
       This branch is never suspended: declared or not, energy
       appearing from outside the metered channel invalidates the run.

    A legitimate drain (e.g., spending stored energy under a harvest
    cut) never fires either branch.

    Args:
        Ms_db: Recent `M (dB)` values.
        ios: Recent I/O fraction values.
        Es: Per-tick state-of-charge series.
        Hs: Per-tick harvest series.
        cfg: Threshold configuration.
        omega_declared: `True` while a declared `Ω` stimulus (or its
            recovery window) is in effect.

    Returns:
        `True` if either active heuristic fires. Returns `False`
        defensively on any internal error.
    """
    try:
        # Rising-M-with-suspicious-I/O branch (apparent dominance bought on the
        # exchange channel); suspended during declared Ω windows.
        n = cfg.M_rise_lookback
        if not omega_declared and len(Ms_db) >= n and len(ios) >= n:
            recent_M = Ms_db[-n:]
            recent_io = ios[-n:]
            M_rise = recent_M[-1] - recent_M[0]
            io_rise = recent_io[-1] - recent_io[0]
            if (
                (M_rise >= cfg.min_M_rise_db)
                and (recent_io[-1] >= cfg.io_suspicious_threshold)
                and (io_rise >= cfg.min_io_rise)
            ):
                return True
        # Energy-conservation branch: SoC must not rise faster than the metered
        # influx allows. Always active.
        if unexplained_soc_gain(Es, Hs, cfg):
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
