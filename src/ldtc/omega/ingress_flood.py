"""Ingress-flood stimulus.

Generates a burst of external demand and I/O traffic to stress the
exchange channels while the controller tries to maintain loop
dominance. Used to test SC1 recovery and smell-tests in the
verification pipeline.

See Also:
    `paper/main.tex`: Verification Pipeline; Signatures B and C; `Ω`
    battery.
"""

from __future__ import annotations

from typing import Dict

from ..plant.adapter import PlantAdapter


def apply(adapter: PlantAdapter, mult: float = 3.0) -> Dict[str, float | str]:
    """Apply an ingress-flood event via the plant adapter.

    Args:
        adapter: Plant interface to which the `Ω` stimulus will be
            applied.
        mult: Multiplicative factor for demand and I/O during the flood
            (e.g., `3.0` produces a 3x burst).

    Returns:
        Dict with resulting demand and I/O values, e.g., `{"demand":
        float, "io": float}`. Exact keys depend on the adapter.

    Notes:
        The adapter is responsible for the platform-specific behavior.
        This `Ω` is typically wrapped by a partition freeze and
        post-event recovery checks in the CLI orchestration.
    """
    return adapter.apply_omega("ingress_flood", mult=mult)
