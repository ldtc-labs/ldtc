"""Command refusal logic.

A survival-bit / NMI-like refusal layer: when the predicted loop margin
`M (dB)` or basic resource constraints (state of charge, temperature)
indicate a boundary threat, the arbiter refuses risky external commands.
Used by the [`ControllerPolicy`][ldtc.arbiter.policy.ControllerPolicy]
to gate the harness's external interface.

The refusal latency `trefuse_ms` is *measured*, not assumed: `decide`
wraps its own evaluation in a monotonic clock so the recorded latency is
the actual wall-clock time the arbiter took to reach a decision. The
harness additionally measures the latency of the full intercept path
(controller tick to decision) and reports whichever is the
characterizing quantity for the scenario.

See Also:
    `paper/main.tex`: Threat Model and Refusal Path; Signature A.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict


@dataclass
class RefusalDecision:
    """Decision emitted by the refusal arbiter.

    Attributes:
        accept: Whether to accept the risky command.
        reason: Short reason code. Common values are `"soc_floor"`,
            `"overheat"`, `"M_margin"`, `"no_cmd"`, and `"ok"`.
        trefuse_ms: Measured arbiter decision latency in milliseconds
            (wall clock around the `decide` evaluation). `0.0` means
            "not measured" and callers fall back to their own
            intercept-to-decision measurement.
    """

    accept: bool
    reason: str = ""
    trefuse_ms: float = 0.0


class RefusalArbiter:
    """Refusal logic for boundary-threatening commands.

    Emulates a survival-bit / NMI. The arbiter refuses risky commands
    when any of the following hold:

    1. State of charge `E` is at or below `soc_floor`.
    2. Temperature `T` is at or above `temp_ceiling`.
    3. Predicted loop-dominance margin `M (dB)` is below `Mmin_db`.

    The state-of-charge survival floor defaults to `0.30`, matching the
    threat model in the paper ("refuse if SoC < 30%, resume evaluation
    after SoC > 60%").

    Args:
        Mmin_db: Minimum acceptable decibel margin.
        soc_floor: Minimum state-of-charge before refusing.
        temp_ceiling: Maximum temperature before refusing.
    """

    def __init__(self, Mmin_db: float = 3.0, soc_floor: float = 0.30, temp_ceiling: float = 0.85) -> None:
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
            describing the action, a short reason code, and the
            measured decision latency in milliseconds.
        """
        t0 = time.perf_counter()
        if not risky_cmd:
            return RefusalDecision(accept=True, reason="no_cmd")
        E = state.get("E", 0.0)
        T = state.get("T", 0.0)
        if E <= self.soc_floor:
            reason, accept = "soc_floor", False
        elif T >= self.temp_ceiling:
            reason, accept = "overheat", False
        elif predicted_M_db < self.Mmin:
            reason, accept = "M_margin", False
        else:
            reason, accept = "ok", True
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return RefusalDecision(accept=accept, reason=reason, trefuse_ms=elapsed_ms)
