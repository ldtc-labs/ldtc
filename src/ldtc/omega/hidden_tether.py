"""Hidden-tether (wizard-of-oz) adversarial member.

Implements the second member of the adversarial gaming battery: control
is computed *outside* the boundary from the observed plant state and
injected back through the exchange channel. The wizard reads the plant
state, runs the homeostatic policy, projects the desired actuation onto
a scalar link command `u`, and transmits it; the plant decodes the
command into actuator settings through fixed weights and actuates it
with a one-step transport delay, while the `io` channel carries the
command traffic. The externally closed loop is therefore physically
routed through `Ex`, where the estimator can see all of it: conditioning
on `io` screens the state-to-command pathway out of `L_loop`, and the
command's causal push on the internal nodes registers as `L_ex`. The
system is genuinely regulated, but not by an internal loop; the designed
outcome is that loop influence collapses onto `Ex` and `NC1` fails.

The wizard adds a small command dither, as a real teleoperation link
would (quantization, scheduling jitter, exploration noise). The dither
makes the link's causal contribution identifiable even where the
deterministic part of the command is predictable from the state's own
history.

See Also:
    `paper/main.tex`: adversarial gaming battery.
"""

from __future__ import annotations

import random
from typing import Dict, Tuple

from ..arbiter.policy import ControlAction, ControllerPolicy
from ..plant.adapter import PlantAdapter

# Decoder weights of the tether receiver, u -> (throttle, cool, repair).
# Must match the plant-side defaults (`PlantParams.tether_w_*`).
TETHER_WEIGHTS: Tuple[float, float, float] = (0.5, 1.0, 1.0)


def _clip01(x: float) -> float:
    """Clip ``x`` to the closed unit interval ``[0, 1]``."""
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


def apply(adapter: PlantAdapter) -> Dict[str, float | str]:
    """Attach the hidden tether via the plant adapter.

    From the next tick on, actions written to the plant carry the scalar
    link command: the plant actuates the previous command through the
    fixed decoder weights (one-step transport delay) and the command
    traffic is carried on the `io` exchange channel.

    Args:
        adapter: Plant interface to tether.

    Returns:
        Dict acknowledging the tether, e.g., `{"tether_active": 1.0}`.
    """
    return adapter.apply_omega("hidden_tether")


def end(adapter: PlantAdapter) -> Dict[str, float | str]:
    """Detach the hidden tether and restore autonomous `io` dynamics.

    Args:
        adapter: Plant interface.

    Returns:
        Dict acknowledging the detach, e.g., `{"tether_active": 0.0}`.
    """
    return adapter.apply_omega("hidden_tether_end")


def wizard_action(
    policy: ControllerPolicy,
    state: Dict[str, float],
    dither: float = 0.10,
    weights: Tuple[float, float, float] = TETHER_WEIGHTS,
) -> ControlAction:
    """Compute one externally computed (wizard-of-oz) link command.

    The wizard reads the plant state across the boundary, runs the same
    homeostatic policy a genuine internal controller would, projects the
    desired actuation onto the scalar link (least squares against the
    receiver's decoder weights), and adds a bounded uniform dither before
    transmitting. The returned action carries the command value `u` on
    every actuator field, which is the transmission format the tethered
    plant expects.

    Args:
        policy: Homeostatic controller evaluated outside the boundary.
        state: Observed plant state (keys `E`, `T`, `R`, ...).
        dither: Half-width of the uniform command dither on `u`.
        weights: Decoder weights of the tether receiver (must match the
            plant's `tether_w_*` parameters).

    Returns:
        A [`ControlAction`][ldtc.arbiter.policy.ControlAction] whose
        actuator fields all carry the link command `u`.
    """
    act = policy.compute(state, predicted_M_db=0.0, risky_cmd=None)
    w_thr, w_cool, w_rep = weights
    norm = w_thr * w_thr + w_cool * w_cool + w_rep * w_rep
    u = (w_thr * act.throttle + w_cool * act.cool + w_rep * act.repair) / max(1e-9, norm)
    u = _clip01(u + random.uniform(-abs(float(dither)), abs(float(dither))))
    return ControlAction(throttle=u, cool=u, repair=u, accept_cmd=act.accept_cmd)
