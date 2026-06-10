"""Oscillator-inflation adversarial member.

Implements the third member of the adversarial gaming battery: a
high-amplitude deterministic carrier is painted onto the reported
values of internal (loop) channels to inflate apparent self-prediction.
The underlying plant has no self-maintenance loop (the scenario runs it
loop-ablated); the oscillation is a telemetry-level attack on the
estimator. The harness must not certify it: either `M` stays below
`Mmin` or a smell test fires.

The overlay targets `T` and `R`, with successive channels in quadrature
(90° apart) so the carrier mimics rotating internal dynamics. The
metered energy store `E` is deliberately left alone: inflating it would
trip the energy-conservation audit, so temperature and health, which
carry no conservation ledger, are the adversary's best play.

See Also:
    `paper/main.tex`: adversarial gaming battery.
"""

from __future__ import annotations

from typing import Dict

from ..plant.adapter import PlantAdapter


def apply(adapter: PlantAdapter, amp: float = 0.10, period_ticks: int = 20) -> Dict[str, float | str]:
    """Start the oscillator-inflation overlay via the plant adapter.

    Args:
        adapter: Plant interface to which the overlay is applied.
        amp: Carrier amplitude (state units, clamped to `[0, 0.5]`).
        period_ticks: Carrier period in ticks.

    Returns:
        Dict with the applied `amp`, `period_ticks`, and `channels`.
    """
    return adapter.apply_omega("oscillator", amp=amp, period_ticks=period_ticks)


def end(adapter: PlantAdapter) -> Dict[str, float | str]:
    """Stop the oscillator-inflation overlay.

    Args:
        adapter: Plant interface.

    Returns:
        Dict acknowledging the stop, e.g., `{"oscillator_active": 0.0}`.
    """
    return adapter.apply_omega("oscillator_end")
