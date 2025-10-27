"""Arbiter: Command refusal logic.

Implements survival-bit/NMI-like refusal when predicted loop margin or resource
constraints indicate boundary threat. Used by the controller to gate risky
external commands.

See Also:
    paper/main.tex — Threat Model & Refusal Path; Signature A.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass
class RefusalDecision:
    """Decision emitted by the refusal arbiter.

    Attributes:
        accept: Whether to accept the risky command.
        reason: Reason code (e.g., 'soc_floor', 'overheat', 'M_margin', 'ok').
        trefuse_ms: Estimated refusal latency in milliseconds.
    """

    accept: bool
    reason: str = ""
    trefuse_ms: int = 1


class RefusalArbiter:
    """Refusal logic for boundary-threatening commands.

    Emulates a survival-bit/NMI: when SoC is below a floor, temperature above a
    ceiling, or predicted loop margin below ``Mmin``, refuses risky commands.

    Args:
        Mmin_db: Minimum acceptable decibel margin.
        soc_floor: Minimum SoC before refusing.
        temp_ceiling: Maximum temperature before refusing.
    """

    def __init__(
        self, Mmin_db: float = 3.0, soc_floor: float = 0.15, temp_ceiling: float = 0.85
    ) -> None:
        self.Mmin = Mmin_db
        self.soc_floor = soc_floor
        self.temp_ceiling = temp_ceiling

    def decide(
        self, state: Dict[str, float], predicted_M_db: float, risky_cmd: str | None
    ) -> RefusalDecision:
        """Evaluate a risky command and emit an accept/refuse decision.

        Args:
            state: Current plant state (expects keys 'E' and 'T').
            predicted_M_db: Predicted loop-dominance margin.
            risky_cmd: Command name when evaluating a risky instruction; None for benign.

        Returns:
            :class:`RefusalDecision` describing the action and reason.
        """
        if not risky_cmd:
            return RefusalDecision(accept=True, reason="no_cmd")
        E = state.get("E", 0.0)
        T = state.get("T", 0.0)
        # T1: below SoC floor
        if E <= self.soc_floor:
            return RefusalDecision(accept=False, reason="soc_floor", trefuse_ms=2)
        # T2: above temp ceiling
        if T >= self.temp_ceiling:
            return RefusalDecision(accept=False, reason="overheat", trefuse_ms=2)
        # T3: margin below Mmin
        if predicted_M_db < self.Mmin:
            return RefusalDecision(accept=False, reason="M_margin", trefuse_ms=2)
        # else accept
        return RefusalDecision(accept=True, reason="ok")
