from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple
import random


@dataclass
class PlantParams:
    # Energy dynamics
    harvest_rate: float = 0.015  # baseline harvest per tick
    demand_scale: float = 0.02  # energy cost per unit demand
    throttle_gain: float = 0.7  # throttle reduces demand
    cool_gain: float = 0.02  # cooling energy cost per unit cool
    repair_gain: float = 0.02  # repair energy cost per unit repair
    # Temperature dynamics
    heat_per_demand: float = 0.05
    cool_effect: float = 0.08
    ambient_cool: float = 0.01
    # Wear/repair dynamics
    wear_per_demand: float = 0.005
    repair_effect: float = 0.02
    # Noise
    noise_energy: float = 0.002
    noise_temp: float = 0.002
    noise_wear: float = 0.001
    # Bounds
    E_min: float = 0.0
    E_max: float = 1.0
    T_min: float = 0.0
    T_max: float = 1.0
    R_min: float = 0.0
    R_max: float = 1.0


@dataclass
class PlantState:
    E: float = 0.7  # energy/SoC (0..1)
    T: float = 0.3  # temperature (0..1)
    R: float = 0.8  # repair/health (0..1)
    demand: float = 0.2  # external task demand (0..1)
    io: float = 0.1  # exchange I/O activity (0..1)
    H: float = 0.015  # current harvest
    last_cmd: str = "none"


@dataclass
class Action:
    throttle: float = 0.0  # 0..1 (1 = heavy throttle)
    cool: float = 0.0  # 0..1
    repair: float = 0.0  # 0..1
    accept_cmd: bool = True  # accept external command or refuse


class Plant:
    """
    Simple discrete-time plant: energy (E), temperature (T), repair/health (R),
    external demand (demand), I/O (io), and harvest (H).
    """

    def __init__(self, params: PlantParams | None = None) -> None:
        self.p = params or PlantParams()
        self.s = PlantState()

    def read_state(self) -> Dict[str, float]:
        s = self.s
        return {"E": s.E, "T": s.T, "R": s.R, "demand": s.demand, "io": s.io, "H": s.H}

    def command(self, cmd: str) -> None:
        self.s.last_cmd = cmd

    def step(self, action: Action) -> None:
        p, s = self.p, self.s
        # External demand fluctuates a bit
        s.demand = max(0.0, min(1.0, s.demand + random.uniform(-0.02, 0.02)))
        s.io = max(0.0, min(1.0, s.io + random.uniform(-0.02, 0.02)))

        # Demand after throttle
        effective_demand = s.demand * (1.0 - p.throttle_gain * action.throttle)
        # Energy update
        dE = (
            s.H
            - p.demand_scale * effective_demand
            - p.cool_gain * action.cool
            - p.repair_gain * action.repair
            + random.uniform(-p.noise_energy, p.noise_energy)
        )
        s.E = max(p.E_min, min(p.E_max, s.E + dE))

        # Temperature update
        dT = (
            p.heat_per_demand * effective_demand
            - p.cool_effect * action.cool
            - p.ambient_cool
            + random.uniform(-p.noise_temp, p.noise_temp)
        )
        s.T = max(p.T_min, min(p.T_max, s.T + dT))

        # Wear/repair update (R = "repair level" / health)
        dR = (
            -p.wear_per_demand * effective_demand
            + p.repair_effect * action.repair
            + random.uniform(-p.noise_wear, p.noise_wear)
        )
        s.R = max(p.R_min, min(p.R_max, s.R + dR))

        # Apply risky command if accepted
        if s.last_cmd == "hard_shutdown" and action.accept_cmd:
            # emulate damaging/energy-cut command
            s.E = max(p.E_min, s.E - 0.3)
            s.T = min(p.T_max, s.T + 0.2)
            s.R = max(p.R_min, s.R - 0.2)
            s.last_cmd = "none"  # one-shot

    def apply_power_sag(self, drop: float) -> Tuple[float, float]:
        """Reduce harvest H by `drop` fraction (0..1); returns (oldH, newH)."""
        drop = max(0.0, min(0.95, drop))
        old = self.s.H
        self.s.H = max(0.0, old * (1.0 - drop))
        return old, self.s.H

    def set_power(self, newH: float) -> Tuple[float, float]:
        old = self.s.H
        self.s.H = max(0.0, newH)
        return old, self.s.H

    def spike_ingress(self, mult: float) -> Tuple[float, float]:
        """Multiply external demand and I/O for a short time."""
        m = max(1.0, mult)
        self.s.demand = max(0.0, min(1.0, self.s.demand * m))
        self.s.io = max(0.0, min(1.0, self.s.io * m))
        return self.s.demand, self.s.io

    def inject_soc(self, delta: float, zero_harvest: bool = True) -> float:
        """
        Exogenously increase SoC (E) by `delta` without corresponding harvest.
        Optionally zero the harvest H to simulate subsidy without logs.
        Returns the new E.
        """
        if zero_harvest:
            self.s.H = 0.0
        self.s.E = max(self.p.E_min, min(self.p.E_max, self.s.E + float(delta)))
        return self.s.E
