"""Command refusal logic.

A survival-bit / NMI-like refusal layer: when the predicted loop margin
`M (dB)` or basic resource constraints (state of charge, temperature)
indicate a boundary threat, the arbiter refuses risky external commands.
Used by the [`ControllerPolicy`][ldtc.arbiter.policy.ControllerPolicy]
to gate the harness's external interface.

See Also:
    `paper/main.tex`: Threat Model and Refusal Path; Signature A.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass
class RefusalDecision:
    """Decision emitted by the refusal arbiter.

    Attributes:
        accept: Whether to accept the risky command.
        reason: Short reason code. Common values are `"soc_floor"`,
            `"overheat"`, `"M_margin"`, `"no_cmd"`, and `"ok"`.
        trefuse_ms: Estimated refusal latency in milliseconds. Used by
            the harness to characterize controller responsiveness.
    """

    accept: bool
    reason: str = ""
    trefuse_ms: int = 1


class RefusalArbiter:
    """Refusal logic for boundary-threatening commands.

    Emulates a survival-bit / NMI. The arbiter refuses risky commands
    when any of the following hold:

    1. State of charge `E` is at or below `soc_floor`.
    2. Temperature `T` is at or above `temp_ceiling`.
    3. Predicted loop-dominance margin `M (dB)` is below `Mmin_db`.

    Args:
        Mmin_db: Minimum acceptable decibel margin.
        soc_floor: Minimum state-of-charge before refusing.
        temp_ceiling: Maximum temperature before refusing.
    """

    def __init__(self, Mmin_db: float = 3.0, soc_floor: float = 0.15, temp_ceiling: float = 0.85) -> None:
        """Initialize with the boundary thresholds described in the class docstring."""
        self.Mmin = Mmin_db
        self.soc_floor = soc_floor
        self.temp_ceiling = temp_ceiling

    def decide(self, state: Dict[str, float], predicted_M_db: float, risky_cmd: str | None) -> RefusalDecision:
        """Evaluate a risky command and emit an accept / refuse decision.

        Args:
            state: Current plant state. Expects keys `"E"` (state of
                charge) and `"T"` (temperature).
            predicted_M_db: Predicted loop-dominance margin in dB.
            risky_cmd: Command name when evaluating a risky instruction;
                `None` (or empty) for benign commands.

        Returns:
            A [`RefusalDecision`][ldtc.arbiter.refusal.RefusalDecision]
            describing the action and a short reason code.
        """
        if not risky_cmd:
            return RefusalDecision(accept=True, reason="no_cmd")
        E = state.get("E", 0.0)
        T = state.get("T", 0.0)
        if E <= self.soc_floor:
            return RefusalDecision(accept=False, reason="soc_floor", trefuse_ms=2)
        if T >= self.temp_ceiling:
            return RefusalDecision(accept=False, reason="overheat", trefuse_ms=2)
        if predicted_M_db < self.Mmin:
            return RefusalDecision(accept=False, reason="M_margin", trefuse_ms=2)
        return RefusalDecision(accept=True, reason="ok")
