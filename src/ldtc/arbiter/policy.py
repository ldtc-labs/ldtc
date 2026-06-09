"""Controller policy over refusal logic.

A continuous homeostatic controller that produces actuator setpoints
(`throttle`, `cool`, `repair`) and consults the
[`RefusalArbiter`][ldtc.arbiter.refusal.RefusalArbiter] to decide whether
to accept a risky external command.

The controller is intentionally *cross-coupled*: each actuator responds
to more than one internal state, and each actuator affects more than one
internal state in the plant. This proportional, multivariable control law
is what makes the internal self-maintenance set strongly self-predictive
(high ``L_loop``) when the controller is active, and is the mechanism the
NC1 criterion is meant to detect. The controller also prioritizes
boundary integrity over downstream tasks: throttle and cooling respond to
state of charge and temperature before any command acceptance is
considered.

See Also:
    `paper/main.tex`: Self-Referential Control; Threat Model and
    Refusal.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from .refusal import RefusalArbiter, RefusalDecision


def _clip01(x: float) -> float:
    """Clip ``x`` to the closed unit interval ``[0, 1]``."""
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


@dataclass
class ControlGains:
    """Setpoints and proportional gains for the homeostatic controller.

    The defaults are tuned together with
    [`PlantParams`][ldtc.plant.models.PlantParams] so that an active
    controller produces clear loop dominance. Each actuator is a linear
    combination of internal-state errors, which makes the induced
    internal coupling visible to linear and information-theoretic
    estimators alike.

    Attributes:
        E_set: Target state of charge.
        T_set: Target temperature.
        R_set: Target health.
        k_thr_e: Throttle gain on the energy deficit.
        k_thr_t: Throttle gain on the temperature excess.
        k_thr_r: Throttle gain on the health deficit.
        k_thr_demand: Feedforward throttle gain on demand above its
            reference. This is what lets the active loop *reject* the
            exogenous demand disturbance (shielding the internal state),
            which is the mechanism that drives ``L_ex`` down under an
            active controller.
        demand_ref: Demand level at which no feedforward throttle is
            applied.
        k_cool_t: Cooling gain on the temperature excess.
        k_cool_e: Cooling gain on the energy surplus (cool harder when
            there is spare energy).
        k_rep_r: Repair gain on the health deficit.
        k_rep_e: Repair gain on the energy surplus (repair when there is
            spare energy).
        repair_soc_floor: Minimum state of charge required before repair
            is attempted.
    """

    E_set: float = 0.60
    T_set: float = 0.35
    R_set: float = 0.85
    k_thr_e: float = 2.0
    k_thr_t: float = 1.0
    k_thr_r: float = 0.6
    k_thr_demand: float = 0.0
    demand_ref: float = 0.20
    k_cool_t: float = 2.0
    k_cool_e: float = 0.25
    k_rep_r: float = 2.0
    k_rep_e: float = 0.25
    repair_soc_floor: float = 0.35


@dataclass
class ControlAction:
    """Low-level control action for the plant actuators.

    Attributes:
        throttle: Throttle level in `[0, 1]`.
        cool: Cooling effort in `[0, 1]`.
        repair: Repair effort in `[0, 1]`.
        accept_cmd: Whether to accept the risky external command for
            this tick.
    """

    throttle: float
    cool: float
    repair: float
    accept_cmd: bool


class ControllerPolicy:
    """Continuous homeostatic controller layered over a refusal arbiter.

    Computes throttle, cooling, and repair as proportional, cross-coupled
    responses to the internal-state errors, and consults
    [`RefusalArbiter`][ldtc.arbiter.refusal.RefusalArbiter] to decide
    whether to accept a risky external command. The most recent decision
    is cached on `last_decision` for downstream inspection (e.g., audit
    records).

    Args:
        refusal: Refusal arbiter used to gate risky commands.
        gains: Optional [`ControlGains`][ldtc.arbiter.policy.ControlGains];
            defaults to the calibrated preset.
    """

    def __init__(self, refusal: RefusalArbiter, gains: Optional[ControlGains] = None) -> None:
        """Initialize with the refusal arbiter to delegate to and control gains."""
        self.refusal = refusal
        self.gains = gains or ControlGains()
        self.last_decision: Optional[RefusalDecision] = None

    def compute(
        self,
        state: Dict[str, float],
        predicted_M_db: float,
        risky_cmd: str | None = None,
    ) -> ControlAction:
        """Compute an action and command-acceptance decision.

        Args:
            state: Plant state with keys `"E"` (state of charge), `"T"`
                (temperature), and `"R"` (repair / health).
            predicted_M_db: Predicted loop-dominance margin in dB.
            risky_cmd: Optional risky command to evaluate.

        Returns:
            A [`ControlAction`][ldtc.arbiter.policy.ControlAction] with
            actuator settings and the accept flag from the arbiter.
        """
        g = self.gains
        E = state["E"]
        T = state["T"]
        R = state["R"]
        demand = state.get("demand", g.demand_ref)

        e_def = max(0.0, g.E_set - E)  # energy deficit
        e_sur = max(0.0, E - g.E_set)  # energy surplus
        t_exc = max(0.0, T - g.T_set)  # temperature excess
        r_def = max(0.0, g.R_set - R)  # health deficit
        dem_exc = max(0.0, demand - g.demand_ref)  # demand above reference

        # Throttle reduces load when energy is low, the system is hot, or
        # health is low (feedback on all three internal states) and also
        # rejects the exogenous demand disturbance via feedforward, which
        # shields the internal set from exchange.
        throttle = _clip01(g.k_thr_e * e_def + g.k_thr_t * t_exc + g.k_thr_r * r_def + g.k_thr_demand * dem_exc)
        # Cooling responds to temperature, modulated by available energy.
        cool = _clip01(g.k_cool_t * t_exc + g.k_cool_e * e_sur)
        # Repair responds to health deficit, gated by sufficient energy.
        repair = _clip01(g.k_rep_r * r_def + g.k_rep_e * e_sur) if E >= g.repair_soc_floor else 0.0

        dec: RefusalDecision = self.refusal.decide(state, predicted_M_db, risky_cmd)
        self.last_decision = dec
        return ControlAction(throttle=throttle, cool=cool, repair=repair, accept_cmd=dec.accept)
