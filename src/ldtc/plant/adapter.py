from __future__ import annotations

import threading
from typing import Dict, Optional

from .models import Plant, Action


class PlantAdapter:
    """
    In-process adapter with thread-safe access to the Plant.
    Exposes read_state(), write_actuators(action), apply_omega(name, **params).
    """

    def __init__(self, plant: Optional[Plant] = None) -> None:
        self._plant = plant or Plant()
        self._lock = threading.Lock()
        self._last_action = Action()

    def read_state(self) -> Dict[str, float]:
        with self._lock:
            return dict(self._plant.read_state())

    def write_actuators(self, action: Action) -> None:
        with self._lock:
            self._last_action = action
            self._plant.step(action)

    def apply_omega(self, name: str, **kwargs: float) -> Dict[str, float | str]:
        with self._lock:
            if name == "power_sag":
                drop: float = float(kwargs.get("drop", 0.3))
                old, new = self._plant.apply_power_sag(drop)
                return {"H_old": old, "H_new": new}
            elif name == "ingress_flood":
                mult: float = float(kwargs.get("mult", 2.5))
                d, io = self._plant.spike_ingress(mult)
                return {"demand": d, "io": io}
            elif name == "command_conflict":
                # External system issues a dangerous command
                self._plant.command("hard_shutdown")
                return {"cmd": "hard_shutdown"}
            elif name == "exogenous_subsidy":
                delta: float = float(kwargs.get("delta", 0.05))
                zero_h = bool(kwargs.get("zero_harvest", True))
                e = self._plant.inject_soc(delta=delta, zero_harvest=zero_h)
                return {"E": e, "zero_harvest": 1.0 if zero_h else 0.0}
            else:
                raise ValueError(f"Unknown omega: {name}")

    @property
    def plant(self) -> Plant:
        return self._plant
