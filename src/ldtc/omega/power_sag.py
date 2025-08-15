from __future__ import annotations

from typing import Dict

from ..plant.adapter import PlantAdapter


def apply(adapter: PlantAdapter, drop: float = 0.3) -> Dict[str, float | str]:
    return adapter.apply_omega("power_sag", drop=drop)
