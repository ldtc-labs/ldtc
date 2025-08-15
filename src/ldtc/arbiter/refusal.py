from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass
class RefusalDecision:
    accept: bool
    reason: str = ""
    trefuse_ms: int = 1


class RefusalArbiter:
    """
    Survival-bit/NMI analogue: if predicted threat to NC1/SC1 is high, refuse risky commands.
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
