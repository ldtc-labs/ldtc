"""Omega: Power-sag stimulus.

Reduces harvest/power input for a bounded interval to test resilience (SC1)
and loop-dominance recovery. The CLI uses this omega to produce verification
timelines and SC1 tables.

See Also:
    paper/main.tex — SC1 and the Ω battery.
"""

from __future__ import annotations

from typing import Dict

from ..plant.adapter import PlantAdapter


def apply(adapter: PlantAdapter, drop: float = 0.3) -> Dict[str, float | str]:
    """Apply a power-sag event via the plant adapter.

    Args:
        adapter: Plant interface to which the omega stimulus will be applied.
        drop: Fractional reduction (0..1) in harvest power during the sag.

    Returns:
        Dict with pre/post harvest values, e.g., ``{"H_old": float,
        "H_new": float}``.

    Notes:
        Higher-level orchestration (CLI) controls the sag duration and recovery
        observation window; this function triggers the sag at the adapter.
    """
    return adapter.apply_omega("power_sag", drop=drop)
