"""In-process plant adapter.

Thread-safe adapter around the software [`Plant`][ldtc.plant.models.Plant]
providing a stable, narrow API used by the CLI and the
[`omega`][ldtc.omega] modules. Mirrors
[`HardwarePlantAdapter`][ldtc.plant.hw_adapter.HardwarePlantAdapter] so
the same `omega` code paths work in simulation and on real hardware.

See Also:
    `paper/main.tex`: Plant models and adapters.
"""

from __future__ import annotations

import threading
from typing import Dict, Optional

from .models import Action, Plant


class PlantAdapter:
    """Thread-safe, in-process adapter over the software plant.

    Exposes a stable API used by the CLI and `Ω` modules:

    - [`read_state`][ldtc.plant.adapter.PlantAdapter.read_state]
    - [`write_actuators`][ldtc.plant.adapter.PlantAdapter.write_actuators]
    - [`apply_omega`][ldtc.plant.adapter.PlantAdapter.apply_omega]

    Args:
        plant: Optional preconstructed
            [`Plant`][ldtc.plant.models.Plant] instance. A fresh
            default-parameterized `Plant` is created if omitted.
    """

    def __init__(self, plant: Optional[Plant] = None) -> None:
        """Initialize with an optional preconstructed plant."""
        self._plant = plant or Plant()
        self._lock = threading.Lock()
        self._last_action = Action()

    def read_state(self) -> Dict[str, float]:
        """Read the current plant state.

        Returns:
            Dict mapping each state key to a float representing the
            plant state at the current tick.
        """
        with self._lock:
            return dict(self._plant.read_state())

    def write_actuators(self, action: Action) -> None:
        """Apply an action to the plant in a thread-safe manner.

        Args:
            action: Actuator settings to apply.
        """
        with self._lock:
            self._last_action = action
            self._plant.step(action)

    def apply_omega(self, name: str, **kwargs: float) -> Dict[str, float | str]:
        """Apply an `Ω` stimulus to the plant.

        Args:
            name: `Ω` name. Recognized values are `"power_sag"`,
                `"ingress_flood"`, `"command_conflict"`, and
                `"exogenous_subsidy"`.
            **kwargs: Parameters forwarded to the underlying plant
                method (e.g., `drop=0.3` for `power_sag`).

        Returns:
            Small dict summarizing the applied stimulus and resulting
            state. The exact keys depend on the `Ω`.

        Raises:
            ValueError: If `name` is not a recognized `Ω`.
        """
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
        """The wrapped [`Plant`][ldtc.plant.models.Plant] instance."""
        return self._plant
