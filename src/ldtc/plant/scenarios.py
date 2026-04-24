"""Scenario parameter presets.

Helpers to construct
[`PlantParams`][ldtc.plant.models.PlantParams] for the baseline,
low-power, and hot-ambient scenarios used in the paper figures and CLI
profiles.

See Also:
    `paper/main.tex`: Plant models and adapters.
"""

from __future__ import annotations

from .models import PlantParams


def default_params() -> PlantParams:
    """Return the default parameter set for the software plant.

    Returns:
        A new [`PlantParams`][ldtc.plant.models.PlantParams] with the
        baseline values.
    """
    return PlantParams()


def low_power_params() -> PlantParams:
    """Return parameters for a low-power scenario.

    Returns:
        [`PlantParams`][ldtc.plant.models.PlantParams] with a reduced
        baseline harvest rate.
    """
    p = PlantParams()
    p.harvest_rate = 0.008
    return p


def hot_ambient_params() -> PlantParams:
    """Return parameters for a hot-ambient scenario.

    Returns:
        [`PlantParams`][ldtc.plant.models.PlantParams] with ambient
        cooling disabled (`ambient_cool = 0.0`).
    """
    p = PlantParams()
    p.ambient_cool = 0.0
    return p
