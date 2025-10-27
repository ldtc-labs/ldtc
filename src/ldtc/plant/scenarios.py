"""Plant: Scenario parameter presets.

Helpers to construct parameter sets for baseline, low-power, and hot-ambient
scenarios for the software plant.

See Also:
    paper/main.tex — Plant models and adapters.
"""

from __future__ import annotations

from .models import PlantParams


def default_params() -> PlantParams:
    """Return default parameter set for the software plant.

    Returns:
        A new :class:`PlantParams` instance with default values.
    """
    return PlantParams()


def low_power_params() -> PlantParams:
    """Return parameters for a low-power scenario.

    Returns:
        :class:`PlantParams` with reduced baseline harvest rate.
    """
    p = PlantParams()
    p.harvest_rate = 0.008
    return p


def hot_ambient_params() -> PlantParams:
    """Return parameters for a hot-ambient scenario.

    Returns:
        :class:`PlantParams` with ambient cooling disabled.
    """
    p = PlantParams()
    p.ambient_cool = 0.0
    return p
