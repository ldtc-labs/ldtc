"""Software plant model and data structures.

Defines the minimal discrete-time plant used by adapters and controllers
in the verification harness, along with its parameter, state, and action
data classes.

The plant is deliberately structured so that loop dominance is a *real,
controllable* property rather than an artifact of the estimator. The three
internal nodes (``E`` energy, ``T`` temperature, ``R`` repair / health)
form a self-maintenance set ``C``. In the *loop-engaged* regime they are
coupled to one another through two pathways: intrinsic regulatory cross
terms (``c_TE``, ``c_RT``, ``c_RE``) and the homeostatic actuators
(``throttle``, ``cool``, ``repair``) that the
[`ControllerPolicy`][ldtc.arbiter.policy.ControllerPolicy] drives from the
internal state. Together these make each internal node strongly
predictable from the recent values of the others (high ``L_loop``) while
the exchange nodes (``demand``, ``io``, ``H``) are shielded down to weak
external drivers (low ``L_ex``).

The *loop-ablated* regime (``loop_engaged=False``) is the matched negative
control: the internal coupling is removed entirely and each internal node
instead passively tracks its own exogenous channel, so exchange dominates
and loop dominance collapses. Note that this is an ablation of the whole
self-maintenance loop (intrinsic coupling plus actuation), not merely a
zeroing of the actuator commands; it realizes the "same boundary, no loop"
contrast that NC1 is supposed to detect.

See Also:
    `paper/main.tex`: Plant models and adapters; Criterion (C/Ex
    partition).
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass
class PlantParams:
    """Physics coefficients governing the software plant dynamics.

    The defaults are calibrated (see ``scripts`` and the tuning notes in
    the repository) so that a controller-in-the-loop run exhibits clear
    loop dominance while a controller-disabled run does not.

    Attributes:
        harvest_rate: Baseline harvest per tick (sets ``H`` when not
            perturbed).
        demand_mean: Mean of the exogenous task-demand process.
        demand_ar: Mean-reversion (AR) pull of the demand process toward
            ``demand_mean``; keeps demand stationary for the estimators.
        demand_noise: Uniform noise magnitude injected into demand.
        io_mean: Mean of the exogenous I/O process.
        io_ar: Mean-reversion pull of the I/O process.
        io_noise: Uniform noise magnitude injected into I/O.
        io_cost: Small energy cost per unit I/O (gives ``io`` a weak,
            honest exchange influence on ``E``).
        demand_scale: Energy cost per unit effective demand.
        throttle_gain: Fraction of demand removed at full throttle.
        cool_gain: Energy cost per unit cooling.
        repair_gain: Energy cost per unit repair.
        act_heat: Heat generated per unit actuator effort
            (``throttle + repair``). This is the dominant, *internal*
            heat source: it depends on the controller's actions, which
            are functions of the internal state, so it couples the
            internal nodes to one another.
        heat_per_demand: Heat added per unit effective demand. Kept
            small so that exogenous demand has only a weak *direct*
            influence on temperature; it is the residual heat path that
            lets the controller-disabled negative control show exchange
            dominance instead of going inert.
        cool_effect: Temperature reduction per unit cooling.
        ambient_cool: Passive ambient cooling per tick.
        wear_per_demand: Health lost per unit effective demand.
        repair_effect: Health gained per unit repair.
        heat_wear: Health lost per unit temperature above the comfort
            band (a small intrinsic ``T -> R`` coupling).
        noise_energy: Uniform noise magnitude for energy.
        noise_temp: Uniform noise magnitude for temperature.
        noise_wear: Uniform noise magnitude for health.
        E_min: Minimum bound for energy.
        E_max: Maximum bound for energy.
        T_min: Minimum bound for temperature.
        T_max: Maximum bound for temperature.
        R_min: Minimum bound for repair / health.
        R_max: Maximum bound for repair / health.
        T_comfort: Temperature above which intrinsic heat wear accrues.
    """

    # Homeostatic setpoints (targets the internal loop maintains).
    E_set: float = 0.60
    T_set: float = 0.35
    R_set: float = 0.85
    # Energy / harvest
    harvest_rate: float = 0.010
    # Exchange (exogenous) processes. The mean-reversion is strong (close to
    # white) so that, when the loop is disabled, current demand carries
    # predictive information that the (demand-driven) internal nodes do not
    # already proxy; this is what makes exchange influence identifiable in the
    # negative control.
    demand_mean: float = 0.50
    demand_ar: float = 0.80
    demand_noise: float = 0.08
    io_mean: float = 0.30
    io_ar: float = 0.80
    io_noise: float = 0.08
    io_cost: float = 0.004
    # --- Internal self-maintenance coupling (active only when the loop is
    # engaged). These cross terms make the internal set strongly
    # self-predictive: each internal node is predicted by the recent values of
    # the *other* internal nodes (high L_loop), which is what NC1 detects. The
    # couplings are intentionally large so the internal set carries a rich,
    # mutually-predictable rhythm, while ``damp_engaged`` keeps it bounded.
    #
    # Note there is deliberately *no* additive coupling into E: energy is a
    # conserved store (see ``_step_engaged``), so the E node is coupled to the
    # others only through the metabolic/actuation costs (cooling tracks T, repair
    # tracks R), which is what keeps a harvest cut able to genuinely deplete it.
    c_TE: float = 0.90  # E deviation -> T
    c_RT: float = 0.54  # T deviation -> R
    c_RE: float = 0.66  # E deviation -> R
    # Self mean-reversion of each internal deviation when the loop is engaged.
    # Together with the actuator-mediated regulation this damps the
    # cross-coupled dynamics so they stay near setpoint instead of saturating.
    damp_engaged: float = 0.85
    # Demand coupling *when the loop is engaged* (shielded: the active loop
    # rejects most of the exogenous disturbance).
    demand_scale: float = 0.006
    heat_per_demand: float = 0.004
    wear_per_demand: float = 0.002
    # Fluctuating external supply (third independent exchange channel, active
    # only when the loop is disabled). It drives the passive health node so
    # that each internal node has its own distinct exogenous driver.
    supply_mean: float = 0.50
    supply_ar: float = 0.80
    supply_noise: float = 0.08
    # Coupling *when the loop is disabled* (exposed: passive matter is driven
    # directly by the environment, so exchange dominates). Each node mean-
    # reverts (``passive_leak``) and tracks a distinct exogenous channel's
    # deviation with a one-step lag, so the exchange influence is strong and
    # identifiable while no internal coupling exists.
    passive_leak: float = 0.55
    demand_scale_passive: float = 0.60  # demand -> E
    heat_per_demand_passive: float = 0.60  # io -> T
    wear_per_demand_passive: float = 0.60  # supply (H) -> R
    # Actuator authority (homeostatic regulation layered on the loop)
    throttle_gain: float = 0.9
    cool_gain: float = 0.040
    repair_gain: float = 0.040
    act_heat: float = 0.030
    cool_effect: float = 0.130
    ambient_cool: float = 0.010
    repair_effect: float = 0.060
    heat_wear: float = 0.020
    # Noise (excites the loop so there is something to regulate/predict). The
    # internal nodes are a stable, noise-driven coupled system: this noise is
    # the excitation that, filtered through the cross-coupling, makes each node
    # predictable from the others (a sizeable, stable L_loop) while keeping the
    # state fluctuations small (std ~ 0.03) and well away from the bounds.
    noise_energy: float = 0.024
    noise_temp: float = 0.024
    noise_wear: float = 0.020
    # Bounds
    E_min: float = 0.0
    E_max: float = 1.0
    T_min: float = 0.0
    T_max: float = 1.0
    R_min: float = 0.0
    R_max: float = 1.0
    # Comfort band for intrinsic heat wear
    T_comfort: float = 0.45


@dataclass
class PlantState:
    """State variables for the software plant (`[0, 1]`-normalized).

    Attributes:
        E: Energy / state of charge.
        T: Temperature.
        R: Repair / health level.
        demand: External task demand.
        io: Exchange I/O activity.
        H: Current harvest level.
        last_cmd: Last command received (one-shot; consumed on the next
            `step` if accepted).
    """

    E: float = 0.7  # energy/SoC (0..1)
    T: float = 0.35  # temperature (0..1)
    R: float = 0.85  # repair/health (0..1)
    demand: float = 0.45  # external task demand (0..1)
    io: float = 0.30  # exchange I/O activity (0..1)
    H: float = 0.030  # current harvest
    last_cmd: str = "none"


@dataclass
class Action:
    """Actuator settings for the plant.

    Attributes:
        throttle: Throttle command in `[0, 1]` (`1.0` is heavy
            throttle).
        cool: Cooling command in `[0, 1]`.
        repair: Repair command in `[0, 1]`.
        accept_cmd: Whether to accept the pending risky command.
    """

    throttle: float = 0.0  # 0..1 (1 = heavy throttle)
    cool: float = 0.0  # 0..1
    repair: float = 0.0  # 0..1
    accept_cmd: bool = True  # accept external command or refuse


def _clip(x: float, lo: float, hi: float) -> float:
    """Clip ``x`` to the closed interval ``[lo, hi]``."""
    return lo if x < lo else (hi if x > hi else x)


class Plant:
    """Minimal discrete-time plant with a self-maintaining E/T/R loop.

    Simulates energy (`E`), temperature (`T`), repair / health (`R`),
    external demand, I/O activity, and energy harvest (`H`).

    In the engaged regime the internal nodes are coupled through two
    pathways. Intrinsic regulatory terms propagate deviations between
    nodes (`c_TE`, `c_RT`, `c_RE`), and the actuators add state-dependent
    couplings: ``throttle`` (driven by the internal states) modulates the
    effective demand that heats, drains, and wears the system; ``cool``
    couples temperature back to energy; and ``repair`` couples health
    back to energy. Together these make the internal set strongly
    self-predictive while shielding it from exchange. The loop-ablated
    regime removes all internal coupling and lets each internal node
    passively track its own exchange channel.

    Args:
        params: Optional [`PlantParams`][ldtc.plant.models.PlantParams]
            instance; defaults to the calibrated baseline preset.
    """

    def __init__(self, params: PlantParams | None = None, loop_engaged: bool = True) -> None:
        """Initialize plant with the given (or default) parameters.

        Args:
            params: Optional plant parameters.
            loop_engaged: Whether the internal self-maintenance loop is
                active. When `True` (the positive control) the internal
                cross-coupling is present and the plant is shielded from
                exchange. When `False` (the controller-disabled negative
                control) the coupling is removed and the plant is driven
                directly by exchange.
        """
        self.p = params or PlantParams()
        self.loop_engaged = bool(loop_engaged)
        self.s = PlantState()
        self.s.E = self.p.E_set
        self.s.T = self.p.T_set
        self.s.R = self.p.R_set
        self.s.H = self.p.harvest_rate
        self.s.demand = self.p.demand_mean
        self.s.io = self.p.io_mean
        # Pre-flood (demand_mean, io_mean) saved while a sustained ingress
        # flood is active; None when no flood is in effect.
        self._flood_saved: Tuple[float, float] | None = None

    def set_loop_engaged(self, engaged: bool) -> None:
        """Engage or disengage the internal self-maintenance loop.

        Disengaging removes the internal cross-coupling and exposes the
        plant directly to exchange; this is how the controller-disabled
        negative control is realized.

        Args:
            engaged: `True` to engage the loop, `False` to disengage.
        """
        self.loop_engaged = bool(engaged)

    def read_state(self) -> Dict[str, float]:
        """Read the current plant state.

        Returns:
            Dict with keys `E`, `T`, `R`, `demand`, `io`, `H`.
        """
        s = self.s
        return {"E": s.E, "T": s.T, "R": s.R, "demand": s.demand, "io": s.io, "H": s.H}

    def command(self, cmd: str) -> None:
        """Record a one-shot external command.

        The command is consumed on the next `step` if the action sets
        `accept_cmd=True`; otherwise it remains pending until accepted
        or overwritten.

        Args:
            cmd: Command name (e.g., `"hard_shutdown"`).
        """
        self.s.last_cmd = cmd

    def step(self, action: Action) -> None:
        """Advance the plant by one tick with the given action.

        Updates the exogenous processes (`demand`, `io`) and then the
        internal nodes (`E`, `T`, `R`). The actuator effects are what
        couple the internal nodes to one another. If `last_cmd` is
        `"hard_shutdown"` and the action accepts it, the command is
        applied (large `E` drop, temperature spike, health drop) and
        consumed.

        Args:
            action: Actuator settings to apply this tick.
        """
        p, s = self.p, self.s

        # Internal update first, using the exogenous values that were set on
        # the previous step. This makes exchange drive the internal nodes with
        # a one-step lag, which is exactly what the lagged (Granger-style)
        # estimator measures; driving with the same-step value would make the
        # influence contemporaneous and invisible to the estimator.
        if self.loop_engaged:
            self._step_engaged(action)
        else:
            self._step_passive()

        # Apply risky command if accepted.
        if s.last_cmd == "hard_shutdown" and action.accept_cmd:
            s.E = max(p.E_min, s.E - 0.3)
            s.T = min(p.T_max, s.T + 0.2)
            s.R = max(p.R_min, s.R - 0.2)
            s.last_cmd = "none"  # one-shot

        # Exogenous (exchange) processes: mean-reverting AR(1), stationary.
        # Updated last so the values recorded this tick are the ones that will
        # drive the internal nodes on the next tick (a clean one-step lag).
        s.demand = _clip(
            s.demand + p.demand_ar * (p.demand_mean - s.demand) + random.uniform(-p.demand_noise, p.demand_noise),
            0.0,
            1.0,
        )
        s.io = _clip(
            s.io + p.io_ar * (p.io_mean - s.io) + random.uniform(-p.io_noise, p.io_noise),
            0.0,
            1.0,
        )
        if not self.loop_engaged:
            # A fluctuating external supply is a third independent exchange
            # channel that drives the passive system. In the engaged regime H
            # is held constant (or set by an Ω perturbation), so it does not
            # leak into the shielded loop.
            s.H = _clip(
                s.H + p.supply_ar * (p.supply_mean - s.H) + random.uniform(-p.supply_noise, p.supply_noise),
                0.0,
                1.0,
            )

    def _step_engaged(self, action: Action) -> None:
        """Advance the internal nodes with the self-maintenance loop active.

        The internal nodes are governed by (a) their mutual cross-coupling
        (the loop), (b) homeostatic actuation, and (c) a small, shielded
        exchange disturbance. This is the positive-control regime, in which
        the internal set is strongly self-predictive.
        """
        p, s = self.p, self.s
        throttle = _clip(action.throttle, 0.0, 1.0)
        cool = _clip(action.cool, 0.0, 1.0)
        repair = _clip(action.repair, 0.0, 1.0)

        # Deviations from setpoint drive the internal coupling.
        e = s.E - p.E_set
        tau = s.T - p.T_set
        rho = s.R - p.R_set

        # Demand after throttle; the loop rejects most of the disturbance.
        effective_demand = s.demand * (1.0 - p.throttle_gain * throttle)

        # Energy obeys conservation. E is the running balance of harvest in minus
        # the metabolic/actuation costs out (plus noise); there is deliberately
        # *no* signed coupling that could inject energy. E is still predicted by
        # the other internal nodes through those costs: cooling effort tracks the
        # temperature error and repair effort tracks the health error, so the
        # energy a window spends is a function of recent T and R. That cost-
        # mediated dependence is what the loop estimator picks up for the E row,
        # and because every coupling into E is a non-positive cost, a sustained
        # harvest cut genuinely depletes the store (a hard-shutdown at low SoC is
        # then a real boundary threat). The damping is dissipative-only: surplus
        # energy can always be wasted (term acts when E is above setpoint) but is
        # never created (clamped off below setpoint).
        e_surplus = e if e > 0.0 else 0.0
        dE = (
            s.H
            - p.demand_scale * effective_demand
            - p.cool_gain * cool
            - p.repair_gain * repair
            - p.io_cost * s.io
            - p.damp_engaged * e_surplus
            + random.uniform(-p.noise_energy, p.noise_energy)
        )
        s.E = _clip(s.E + dE, p.E_min, p.E_max)

        dT = (
            p.act_heat * (throttle + repair)
            + p.heat_per_demand * effective_demand
            - p.cool_effect * cool
            - p.ambient_cool
            - p.damp_engaged * tau
            + p.c_TE * e
            + random.uniform(-p.noise_temp, p.noise_temp)
        )
        s.T = _clip(s.T + dT, p.T_min, p.T_max)

        dR = (
            -p.wear_per_demand * effective_demand
            + p.repair_effect * repair
            - p.heat_wear * max(0.0, s.T - p.T_comfort)
            - p.damp_engaged * rho
            + p.c_RT * tau
            - p.c_RE * e
            + random.uniform(-p.noise_wear, p.noise_wear)
        )
        s.R = _clip(s.R + dR, p.R_min, p.R_max)

    def _step_passive(self) -> None:
        """Advance the internal nodes with the self-maintenance loop disabled.

        Passive matter: no internal coupling and no actuation, so the
        internal nodes are driven directly by the exogenous environment
        (and noise). This is the controller-disabled negative control, in
        which exchange dominates and loop dominance is absent.
        """
        p, s = self.p, self.s
        # Each internal node tracks a distinct, independent exchange channel
        # (E<-demand, T<-io, R<-supply H). Because the channels are
        # independent and the drive is lagged, exchange influence is strong
        # and identifiable while no internal (C-to-C) coupling exists.
        dem = s.demand - p.demand_mean
        io_dev = s.io - p.io_mean
        h_dev = s.H - p.supply_mean

        dE = (
            -p.passive_leak * (s.E - p.E_set)
            - p.demand_scale_passive * dem
            + random.uniform(-p.noise_energy, p.noise_energy)
        )
        s.E = _clip(s.E + dE, p.E_min, p.E_max)

        dT = (
            -p.passive_leak * (s.T - p.T_set)
            + p.heat_per_demand_passive * io_dev
            + random.uniform(-p.noise_temp, p.noise_temp)
        )
        s.T = _clip(s.T + dT, p.T_min, p.T_max)

        dR = (
            -p.passive_leak * (s.R - p.R_set)
            + p.wear_per_demand_passive * h_dev
            + random.uniform(-p.noise_wear, p.noise_wear)
        )
        s.R = _clip(s.R + dR, p.R_min, p.R_max)

    def apply_power_sag(self, drop: float) -> Tuple[float, float]:
        """Reduce harvest by a fractional drop.

        Args:
            drop: Fraction in `[0, 0.95]` by which to reduce `H`.
                Values outside the range are clamped.

        Returns:
            Tuple `(old_H, new_H)`.
        """
        drop = max(0.0, min(0.95, drop))
        old = self.s.H
        self.s.H = max(0.0, old * (1.0 - drop))
        return old, self.s.H

    def set_power(self, newH: float) -> Tuple[float, float]:
        """Set the harvest level directly.

        Args:
            newH: New harvest value (negative inputs clamp to `0`).

        Returns:
            Tuple `(old_H, new_H)`.
        """
        old = self.s.H
        self.s.H = max(0.0, newH)
        return old, self.s.H

    def spike_ingress(self, mult: float) -> Tuple[float, float]:
        """Multiply demand and I/O by a factor (one-shot spike).

        This is a transient: the mean-reverting exogenous processes pull
        demand and I/O back to their configured means within a few ticks.
        For a flood that persists for a bounded interval, use
        [`begin_ingress_flood`][ldtc.plant.models.Plant.begin_ingress_flood].

        Args:
            mult: Multiplicative factor (`>= 1.0`). Smaller values are
                clamped up to `1.0`. Results are clamped into `[0, 1]`.

        Returns:
            Tuple of updated `(demand, io)`.
        """
        m = max(1.0, mult)
        self.s.demand = max(0.0, min(1.0, self.s.demand * m))
        self.s.io = max(0.0, min(1.0, self.s.io * m))
        return self.s.demand, self.s.io

    def begin_ingress_flood(self, mult: float) -> Tuple[float, float]:
        """Start a sustained ingress flood.

        Scales the *means* of the demand and I/O processes (and their
        current values) so the exogenous load stays elevated for the
        duration of the flood instead of mean-reverting away within a few
        ticks. The scaled means are capped at `0.95` so the flooded
        channels keep fluctuating (saturating them at `1.0` would destroy
        their variance and degrade the estimators for an uninteresting
        reason). Idempotent while a flood is active.

        Args:
            mult: Multiplicative factor (`>= 1.0`) applied to
                `demand_mean` and `io_mean`.

        Returns:
            Tuple of the new `(demand_mean, io_mean)`.
        """
        m = max(1.0, mult)
        if self._flood_saved is None:
            self._flood_saved = (self.p.demand_mean, self.p.io_mean)
            self.p.demand_mean = min(0.95, self.p.demand_mean * m)
            self.p.io_mean = min(0.95, self.p.io_mean * m)
            self.s.demand = max(0.0, min(1.0, self.s.demand * m))
            self.s.io = max(0.0, min(1.0, self.s.io * m))
        return self.p.demand_mean, self.p.io_mean

    def end_ingress_flood(self) -> Tuple[float, float]:
        """End a sustained ingress flood and restore the process means.

        The current demand and I/O values are left to decay back to the
        restored means through the AR pull (no discontinuous reset), so
        the offset transient is part of the measured recovery.

        Returns:
            Tuple of the restored `(demand_mean, io_mean)`.
        """
        if self._flood_saved is not None:
            self.p.demand_mean, self.p.io_mean = self._flood_saved
            self._flood_saved = None
        return self.p.demand_mean, self.p.io_mean

    def inject_soc(self, delta: float, zero_harvest: bool = True) -> float:
        """Exogenously increase SoC `E` by `delta`.

        Used as the negative-control `Ω` (an "exogenous subsidy") to
        exercise the smell-tests: a controller that survives only because
        energy keeps appearing from nowhere should fail
        [`exogenous_subsidy_red_flag`][ldtc.guardrails.smelltests.exogenous_subsidy_red_flag].

        Args:
            delta: Amount to add to `E`. The result is clamped into
                `[E_min, E_max]`.
            zero_harvest: When `True` (default), also set `H = 0` so
                the boost cannot be confused with real harvest.

        Returns:
            The new `E` value after clamping.
        """
        if zero_harvest:
            self.s.H = 0.0
        self.s.E = max(self.p.E_min, min(self.p.E_max, self.s.E + float(delta)))
        return self.s.E
