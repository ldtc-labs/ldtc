"""Control-outage stimulus.

Ablates the self-maintenance loop itself (rather than stressing its
inputs): the internal cross-coupling and actuation are switched off, so
the internal nodes become passively driven by exchange. This is the
designed-fail member of the `Ω` battery: a perturbation outside the
bounded class that SC1 certifies, so the criterion must report failure
(no bounded-depth, bounded-time recovery of loop dominance).

See Also:
    `paper/main.tex`: SC1 and the `Ω` battery; designed-fail controls.
"""

from __future__ import annotations

from typing import Dict

from ..plant.adapter import PlantAdapter


def apply(adapter: PlantAdapter) -> Dict[str, float | str]:
    """Begin a control outage via the plant adapter.

    Args:
        adapter: Plant interface to which the `Ω` stimulus will be
            applied.

    Returns:
        Dict acknowledging the ablation, e.g., `{"loop_engaged": 0.0}`.

    Notes:
        Higher-level orchestration (the CLI) controls the outage
        duration and, for recoverable outages, restores the loop with
        the `"control_outage_end"` `Ω`, which also restores the metered
        harvest level.
    """
    return adapter.apply_omega("control_outage")


def end(adapter: PlantAdapter) -> Dict[str, float | str]:
    """End a control outage (re-engage the loop) via the adapter.

    Args:
        adapter: Plant interface.

    Returns:
        Dict acknowledging the restoration, e.g., `{"loop_engaged": 1.0}`.
    """
    return adapter.apply_omega("control_outage_end")
