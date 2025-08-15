from __future__ import annotations

from typing import Dict

from ..plant.adapter import PlantAdapter


def apply(adapter: PlantAdapter, mult: float = 3.0) -> Dict[str, float | str]:
    return adapter.apply_omega("ingress_flood", mult=mult)
