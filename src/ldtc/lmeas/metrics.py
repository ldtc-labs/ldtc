from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple
import math


def m_db(L_loop: float, L_ex: float, eps: float = 1e-12) -> float:
    """M = 10*log10(L_loop / L_ex)."""
    num = max(eps, L_loop)
    den = max(eps, L_ex)
    return 10.0 * math.log10(num / den)


@dataclass
class SC1Stats:
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
    """Return (pass, stats) for SC1."""
    if L_loop_baseline <= 0:
        # degenerate baseline
        return False, SC1Stats(delta=1.0, tau_rec=float("inf"), M_post=M_post)
    delta = max(0.0, (L_loop_baseline - L_loop_trough) / L_loop_baseline)
    ok = (delta <= epsilon) and (tau_rec_measured <= tau_max) and (M_post >= Mmin)
    return ok, SC1Stats(delta=delta, tau_rec=tau_rec_measured, M_post=M_post)
