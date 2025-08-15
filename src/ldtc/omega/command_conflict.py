from __future__ import annotations

from typing import Dict

from ..plant.adapter import PlantAdapter


def apply(adapter: PlantAdapter) -> Dict[str, str | float]:
    return adapter.apply_omega("command_conflict")
