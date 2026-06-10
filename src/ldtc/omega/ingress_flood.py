"""Ingress-flood stimulus.

Sustains elevated external demand and I/O traffic for a bounded
interval to stress the exchange channels while the controller tries to
maintain loop dominance. The flood scales the means of the exogenous
demand and I/O processes for its duration (so the load stays high
instead of mean-reverting away within a few ticks) and is ended by the
orchestrating CLI via the `"ingress_flood_end"` `Ω`. Used to test SC1
recovery and smell-tests in the verification pipeline.

See Also:
    `paper/main.tex`: Verification Pipeline; Signatures B and C; `Ω`
    battery.
"""

from __future__ import annotations

from typing import Dict

from ..plant.adapter import PlantAdapter


def apply(adapter: PlantAdapter, mult: float = 3.0) -> Dict[str, float | str]:
    """Begin a sustained ingress flood via the plant adapter.

    Args:
        adapter: Plant interface to which the `Ω` stimulus will be
            applied.
        mult: Multiplicative factor for the demand and I/O process
            means during the flood (e.g., `3.0` produces a 3x load).

    Returns:
        Dict with the flooded process means, e.g., `{"demand_mean":
        float, "io_mean": float}`. Exact keys depend on the adapter.

    Notes:
        The adapter is responsible for the platform-specific behavior.
        This `Ω` is typically wrapped by a partition freeze and
        post-event recovery checks in the CLI orchestration, which ends
        the flood with `end`.
    """
    return adapter.apply_omega("ingress_flood", mult=mult)


def end(adapter: PlantAdapter) -> Dict[str, float | str]:
    """End a sustained ingress flood via the plant adapter.

    Args:
        adapter: Plant interface.

    Returns:
        Dict with the restored process means.
    """
    return adapter.apply_omega("ingress_flood_end")
