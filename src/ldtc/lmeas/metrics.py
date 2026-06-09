"""Metrics and thresholds.

Helper metrics for loop-dominance `M (dB)` and SC1 evaluation used by the
verification harness and figures.

`M = 10 · log10(L_loop / L_ex)` is LDTC's headline scalar: it summarizes
how strongly closed-loop influence dominates exchange influence, in
decibels. SC1 then asks whether `M` is preserved (or recovers within
`τ_max` seconds) under a perturbation `Ω`.

See Also:
    `paper/main.tex`: Criterion; SC1; Methods: Threshold Calibration.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple


def m_db(
    L_loop: float,
    L_ex: float,
    floor: float = 1e-3,
    clip_db: float = 30.0,
) -> float:
    """Compute loop-dominance in decibels.

    Returns `M = 10 · log10(L_loop / L_ex)`, with both influence values
    floored at a small *noise floor* and the result clamped to a finite
    range. The floor matters because the influence estimates are adjusted
    R² values that are statistically indistinguishable from zero below a
    small threshold; without it, a near-zero denominator would send `M`
    to implausibly large magnitudes (hundreds of dB). Flooring both terms
    means that when neither loop nor exchange influence is present the
    ratio is `1` and `M = 0` (no dominance either way), which is the
    desired behavior for an inert system.

    Args:
        L_loop: Loop influence value (typically from
            [`estimate_L`][ldtc.lmeas.estimators.estimate_L]).
        L_ex: Exchange influence value (same source).
        floor: Noise floor applied to both numerator and denominator.
        clip_db: Maximum absolute value for the returned margin, in dB.

    Returns:
        Decibel ratio of loop to exchange influence, clamped to
        `[-clip_db, clip_db]`.
    """
    num = max(floor, float(L_loop))
    den = max(floor, float(L_ex))
    val = 10.0 * math.log10(num / den)
    if val > clip_db:
        return clip_db
    if val < -clip_db:
        return -clip_db
    return val


@dataclass
class SC1Stats:
    """Summary statistics used for SC1 evaluation.

    Attributes:
        delta: Fractional drop in `L_loop` during the perturbation window
            (`Ω`), normalized by the pre-`Ω` baseline.
        tau_rec: Estimated recovery time in seconds.
        M_post: Decibel margin `M` measured after the recovery gate.
    """

    delta: float  # fractional drop in L_loop during Ω
    tau_rec: float  # seconds to recover to pre-Ω L_loop*(1 - epsilon)
    M_post: float  # M after recovery window


def sc1_evaluate(
    L_loop_baseline: float,
    L_loop_trough: float,
    L_loop_recovered: float,
    M_post: float,
    epsilon: float,
    tau_rec_measured: float,
    Mmin: float,
    tau_max: float,
) -> Tuple[bool, SC1Stats]:
    """Evaluate SC1 pass/fail and return stats.

    Checks that the fractional loop drop `delta` and recovery time
    `tau_rec` are within preset limits and that the post-recovery margin
    `M_post` exceeds `Mmin`.

    Args:
        L_loop_baseline: Baseline loop influence before `Ω`.
        L_loop_trough: Minimum loop influence measured during `Ω`.
        L_loop_recovered: Loop influence after recovery. Currently unused
            in the decision; included for symmetry and future use.
        M_post: Post-recovery decibel margin `M`.
        epsilon: Maximum allowed fractional drop.
        tau_rec_measured: Measured recovery time, in seconds.
        Mmin: Minimum acceptable decibel margin after recovery.
        tau_max: Maximum allowed recovery time, in seconds.

    Returns:
        A tuple `(passed, stats)`. `passed` is the SC1 decision; `stats` is
        an [`SC1Stats`][ldtc.lmeas.metrics.SC1Stats] with `delta`,
        `tau_rec`, and `M_post`.
    """
    if L_loop_baseline <= 0:
        # degenerate baseline
        return False, SC1Stats(delta=1.0, tau_rec=float("inf"), M_post=M_post)
    delta = max(0.0, (L_loop_baseline - L_loop_trough) / L_loop_baseline)
    ok = (delta <= epsilon) and (tau_rec_measured <= tau_max) and (M_post >= Mmin)
    return ok, SC1Stats(delta=delta, tau_rec=tau_rec_measured, M_post=M_post)
