"""Lmeas: Metrics and thresholds.

Helper metrics for loop-dominance M(dB) and SC1 evaluation used by the
verification harness and figures.

See Also:
    paper/main.tex — Criterion; SC1; Methods: Threshold Calibration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple
import math


def m_db(L_loop: float, L_ex: float, eps: float = 1e-12) -> float:
    """Compute loop-dominance in decibels.

    Computes ``M = 10 * log10(L_loop / L_ex)`` with small positive floors to
    avoid division by zero.

    Args:
        L_loop: Loop influence value.
        L_ex: Exchange influence value.
        eps: Numerical floor applied to both numerator and denominator.

    Returns:
        Decibel ratio of loop to exchange influence.
    """
    num = max(eps, L_loop)
    den = max(eps, L_ex)
    return 10.0 * math.log10(num / den)


@dataclass
class SC1Stats:
    """Summary statistics used for SC1 evaluation.

    Attributes:
        delta: Fractional drop in ``L_loop`` during the perturbation window.
        tau_rec: Estimated recovery time in seconds.
        M_post: Decibel margin measured after recovery gate.
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

    Checks that the fractional loop drop ``delta`` and recovery time ``tau_rec``
    are within preset limits and that the post-recovery margin exceeds ``Mmin``.

    Args:
        L_loop_baseline: Baseline loop influence before Ω.
        L_loop_trough: Minimum loop influence measured during Ω.
        L_loop_recovered: Loop influence after recovery (unused in decision here).
        M_post: Post-recovery decibel margin ``M``.
        epsilon: Maximum allowed fractional drop.
        tau_rec_measured: Measured recovery time (seconds).
        Mmin: Minimum acceptable decibel margin after recovery.
        tau_max: Maximum allowed recovery time.

    Returns:
        Tuple ``(passed, stats)`` where ``passed`` is the SC1 decision and
        ``stats`` contains ``delta``, ``tau_rec``, and ``M_post``.
    """
    if L_loop_baseline <= 0:
        # degenerate baseline
        return False, SC1Stats(delta=1.0, tau_rec=float("inf"), M_post=M_post)
    delta = max(0.0, (L_loop_baseline - L_loop_trough) / L_loop_baseline)
    ok = (delta <= epsilon) and (tau_rec_measured <= tau_max) and (M_post >= Mmin)
    return ok, SC1Stats(delta=delta, tau_rec=tau_rec_measured, M_post=M_post)
