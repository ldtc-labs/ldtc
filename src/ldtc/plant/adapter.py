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
                `"ingress_flood"` / `"ingress_flood_end"` (sustained
                flood begin / end), `"ingress_spike"` (one-shot),
                `"control_outage"` / `"control_outage_end"` (ablate /
                restore the self-maintenance loop),
                `"command_conflict"`, `"exogenous_subsidy"`,
                `"hidden_tether"` / `"hidden_tether_end"` (route control
                through the exchange channel), and `"oscillator"` /
                `"oscillator_end"` (deterministic carrier overlay on
                internal channels).
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
                dm, im = self._plant.begin_ingress_flood(mult)
                return {"demand_mean": dm, "io_mean": im}
            elif name == "ingress_flood_end":
                dm, im = self._plant.end_ingress_flood()
                return {"demand_mean": dm, "io_mean": im}
            elif name == "ingress_spike":
                mult_s: float = float(kwargs.get("mult", 2.5))
                d, io = self._plant.spike_ingress(mult_s)
                return {"demand": d, "io": io}
            elif name == "control_outage":
                self._plant.set_loop_engaged(False)
                return {"loop_engaged": 0.0}
            elif name == "control_outage_end":
                self._plant.set_loop_engaged(True)
                # Restore the metered harvest level: during the outage H is
                # an exogenous supply process, which must not persist as an
                # unearned energy subsidy once the loop is re-engaged.
                self._plant.set_power(self._plant.p.harvest_rate)
                return {"loop_engaged": 1.0}
            elif name == "command_conflict":
                self._plant.command("hard_shutdown")
                return {"cmd": "hard_shutdown"}
            elif name == "exogenous_subsidy":
                delta: float = float(kwargs.get("delta", 0.05))
                zero_h = bool(kwargs.get("zero_harvest", True))
                e = self._plant.inject_soc(delta=delta, zero_harvest=zero_h)
                return {"E": e, "zero_harvest": 1.0 if zero_h else 0.0}
            elif name == "hidden_tether":
                active = self._plant.begin_tether()
                return {"tether_active": 1.0 if active else 0.0}
            elif name == "hidden_tether_end":
                active = self._plant.end_tether()
                return {"tether_active": 1.0 if active else 0.0}
            elif name == "oscillator":
                # The overlay targets T and R: the adversary's best play, since
                # painting the metered energy store E would trip the
                # conservation audit. Custom channel sets are available via
                # `Plant.begin_oscillator` directly (tests / experiments).
                amp: float = float(kwargs.get("amp", 0.10))
                period: int = int(kwargs.get("period_ticks", 20))
                info = self._plant.begin_oscillator(amp=amp, period_ticks=period, channels=("T", "R"))
                return {**info, "channels": "T,R"}
            elif name == "oscillator_end":
                self._plant.end_oscillator()
                return {"oscillator_active": 0.0}
            else:
                raise ValueError(f"Unknown omega: {name}")

    @property
    def plant(self) -> Plant:
        """The wrapped [`Plant`][ldtc.plant.models.Plant] instance."""
        return self._plant
