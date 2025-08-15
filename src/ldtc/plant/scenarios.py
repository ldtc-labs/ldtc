from __future__ import annotations

from .models import PlantParams


def default_params() -> PlantParams:
    return PlantParams()


def low_power_params() -> PlantParams:
    p = PlantParams()
    p.harvest_rate = 0.008
    return p


def hot_ambient_params() -> PlantParams:
    p = PlantParams()
    p.ambient_cool = 0.0
    return p
