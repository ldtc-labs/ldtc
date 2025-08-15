from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from .refusal import RefusalArbiter, RefusalDecision


@dataclass
class ControlAction:
    throttle: float
    cool: float
    repair: float
    accept_cmd: bool


class ControllerPolicy:
    """
    Simple homeostasis controller:
    - If E low -> throttle up, repair down
    - If T high -> cool up
    - If R low -> repair up when E sufficient
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
