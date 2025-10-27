"""Arbiter: Controller policy over refusal logic.

Provides a simple homeostatic controller that consults the refusal arbiter to
prioritize boundary integrity over risky external commands.

See Also:
    paper/main.tex — Self-Referential Control; Threat Model & Refusal.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from .refusal import RefusalArbiter, RefusalDecision


@dataclass
class ControlAction:
    """Low-level control action for the plant actuators.

    Attributes:
        throttle: Throttle level in [0, 1].
        cool: Cooling effort in [0, 1].
        repair: Repair effort in [0, 1].
        accept_cmd: Whether to accept a risky external command.
    """

    throttle: float
    cool: float
    repair: float
    accept_cmd: bool


class ControllerPolicy:
    """Simple homeostatic controller layered over a refusal arbiter.

    Heuristically sets throttle, cooling, and repair based on current state,
    and consults :class:`RefusalArbiter` to decide whether to accept a risky
    external command.

    Args:
        refusal: Refusal arbiter used to gate risky commands.
    """

    def __init__(self, refusal: RefusalArbiter) -> None:
        self.refusal = refusal
        self.last_decision: Optional[RefusalDecision] = None

    def compute(
        self,
        state: Dict[str, float],
        predicted_M_db: float,
        risky_cmd: str | None = None,
    ) -> ControlAction:
        """Compute an action and command-acceptance decision.

        Args:
            state: Plant state with keys 'E', 'T', and 'R'.
            predicted_M_db: Predicted loop-dominance margin.
            risky_cmd: Optional risky command to evaluate.

        Returns:
            :class:`ControlAction` with actuator settings and accept flag.
        """
        E = state["E"]
        T = state["T"]
        R = state["R"]
        # heuristics
        throttle = 0.0
        cool = 0.0
        repair = 0.0
        if E < 0.4:
            throttle = min(1.0, 0.5 + (0.4 - E))
        if T > 0.6:
            cool = min(1.0, (T - 0.6) * 1.5)
        if R < 0.6 and E > 0.5 and T < 0.7:
            repair = min(1.0, (0.6 - R) * 1.5)
        dec: RefusalDecision = self.refusal.decide(state, predicted_M_db, risky_cmd)
        self.last_decision = dec
        return ControlAction(
            throttle=throttle, cool=cool, repair=repair, accept_cmd=dec.accept
        )
