"""Controller policy over refusal logic.

A small homeostatic controller that produces actuator setpoints
(`throttle`, `cool`, `repair`) and consults the
[`RefusalArbiter`][ldtc.arbiter.refusal.RefusalArbiter] to decide
whether to accept a risky external command. The controller intentionally
prioritizes boundary integrity over downstream tasks: throttle and cool
respond to `E` (state of charge) and `T` (temperature) before any
command acceptance is considered.

See Also:
    `paper/main.tex`: Self-Referential Control; Threat Model and
    Refusal.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from .refusal import RefusalArbiter, RefusalDecision


@dataclass
class ControlAction:
    """Low-level control action for the plant actuators.

    Attributes:
        throttle: Throttle level in `[0, 1]`.
        cool: Cooling effort in `[0, 1]`.
        repair: Repair effort in `[0, 1]`.
        accept_cmd: Whether to accept the risky external command for
            this tick.
    """

    throttle: float
    cool: float
    repair: float
    accept_cmd: bool


class ControllerPolicy:
    """Simple homeostatic controller layered over a refusal arbiter.

    Heuristically sets throttle, cooling, and repair based on the
    current state, and consults
    [`RefusalArbiter`][ldtc.arbiter.refusal.RefusalArbiter] to decide
    whether to accept a risky external command. The most recent
    decision is cached on `last_decision` for downstream inspection
    (e.g., audit records).

    Args:
        refusal: Refusal arbiter used to gate risky commands.
    """

    def __init__(self, refusal: RefusalArbiter) -> None:
        """Initialize with the refusal arbiter to delegate to."""
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
            state: Plant state with keys `"E"` (state of charge), `"T"`
                (temperature), and `"R"` (repair / health).
            predicted_M_db: Predicted loop-dominance margin in dB.
            risky_cmd: Optional risky command to evaluate.

        Returns:
            A [`ControlAction`][ldtc.arbiter.policy.ControlAction] with
            actuator settings and the accept flag from the arbiter.
        """
        E = state["E"]
        T = state["T"]
        R = state["R"]
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
        return ControlAction(throttle=throttle, cool=cool, repair=repair, accept_cmd=dec.accept)
