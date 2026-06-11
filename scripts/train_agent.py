#!/usr/bin/env python3
"""Scripts: Train a self-maintenance policy from scratch (emergence demo).

Trains the tiny pure-NumPy policy of
:mod:`ldtc.plant.policy_controller` on the emergence plant (the
adversarial test plant: no intrinsic internal couplings, actuators with
real authority) with a simple antithetic evolution strategy. The reward
is survival/uptime plus a service term for demand actually served, minus
homeostatic shaping penalties (state-of-charge depletion, overheating,
integrity loss); the episode terminates on boundary failure, and each
episode is stressed by randomized power sags and ingress floods so that
staying alive while serving load genuinely requires state-coupled
control. Nothing in the objective mentions loop dominance, the C/Ex
partition, or the estimator: any loop dominance that emerges is a
byproduct of learned self-maintenance.

The policy is interoceptive by construction: it observes the internal
nodes only (``E``, ``T``, ``R``, settable via ``--obs``), so the learned
control law is a function of the system's own state, exactly like the
hand-coded controller it replaces. The exchange channels act on the
policy only through the plant. This is an experimental design choice,
not a training trick: with exteroceptive inputs the optimizer happily
learns feedforward control from the demand channel, and the harness then
(correctly) attributes part of the control pathway to exchange; the
emergence question, whether *internal-state* feedback arises from a
survival objective, needs the internal-state policy class.

Checkpoints are written at fixed training fractions (by default 0, 10,
25, 50, and 100 percent) so the measurement sweep
(``scripts/emergence.py``) can chart loop dominance against training
progress. Everything is deterministic given ``--seed``.

Run:

    python scripts/train_agent.py --config configs/profile_emergence.yml \
        --out artifacts/emergence

See Also:
    paper/main.tex: Results (loop dominance emerges under learning).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from dataclasses import asdict, dataclass, replace
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

from ldtc.plant.models import Action, Plant, PlantParams  # noqa: E402
from ldtc.plant.policy_controller import MLPPolicy  # noqa: E402

DEFAULT_CHECKPOINT_FRACS = (0.0, 0.10, 0.25, 0.50, 1.0)

# The policy observes the internal state only (see module docstring).
INTEROCEPTIVE_OBS_KEYS: Tuple[str, ...] = ("E", "T", "R")


# --------------------------------------------------------------------------- #
# Episode (environment) definition
# --------------------------------------------------------------------------- #
@dataclass
class EpisodeConfig:
    """Survival episode: dynamics horizon, failure bounds, reward shaping.

    The reward per surviving tick is ``1`` (uptime), plus a service term
    proportional to the demand actually served (demand times the fraction
    not throttled away), minus a capped homeostatic penalty proportional
    to the absolute deviation of each internal node from its setpoint.
    The minimum per-tick reward is positive, so surviving always
    dominates dying. The episode ends early on boundary failure
    (state-of-charge depletion, overheating, or integrity loss).

    The three terms together remove every degenerate optimum a learner
    could otherwise exploit. Uptime alone is satisfied by near-passive
    policies (this plant survives quietly when left alone). The service
    term makes blanket throttling costly, so shedding load must be timed
    to the internal state rather than held constant. The homeostatic
    penalty makes tight regulation pay, and tight regulation against the
    process noise and the randomized perturbations (power sags, ingress
    floods; seeded per episode) is achievable only by state-coupled
    feedback. Nothing in the objective mentions loop dominance, the C/Ex
    partition, or the estimator: any loop dominance that emerges is a
    byproduct of learned self-maintenance under a performance demand.
    """

    max_ticks: int = 400
    # Boundary-failure bounds (episode terminates when crossed).
    fail_E: float = 0.02
    fail_T: float = 0.98
    fail_R: float = 0.02
    # Homeostatic penalty weights on |node - setpoint| (setpoints come from
    # the plant parameters) and the total penalty cap per tick. The weights
    # are deliberately strong: near-passive survival must pay visibly less
    # than tight regulation, otherwise the reward landscape is flat around
    # do-nothing policies. The energy weight is the smallest because a
    # power sag depletes the store no matter what the policy does; the
    # controllable terms (T, R) carry most of the shaping pressure.
    w_E: float = 1.5
    w_T: float = 6.0
    w_R: float = 8.0
    penalty_cap: float = 0.95
    # Service reward per unit of served demand (demand after throttling).
    # This is the task-performance pressure: it puts an opportunity cost on
    # throttling, so load shedding is worth it only when the internal state
    # calls for it.
    w_serve: float = 0.6
    # Randomized perturbations (per-episode schedule). Calibrated against
    # the emergence plant so that a state-aware policy can ride out a
    # worst-case sag-flood overlap while state-blind policies cannot
    # hold all three nodes at once.
    p_sag: float = 0.85
    sag_drop: Tuple[float, float] = (0.4, 0.75)
    sag_start: Tuple[int, int] = (60, 180)
    sag_dur: Tuple[int, int] = (50, 110)
    p_flood: float = 0.85
    flood_mult: Tuple[float, float] = (2.0, 5.0)
    flood_start: Tuple[int, int] = (60, 250)
    flood_dur: Tuple[int, int] = (40, 120)


def _tick_reward(
    E: float,
    T: float,
    R: float,
    served: float,
    params: PlantParams,
    cfg: EpisodeConfig,
) -> float:
    """Per-tick reward: uptime plus service minus capped setpoint penalties.

    Args:
        E: Energy after the step.
        T: Temperature after the step.
        R: Health after the step.
        served: Demand actually served this tick (demand times the
            unthrottled fraction).
        params: Plant parameters (source of the setpoints).
        cfg: Episode configuration (weights and cap).

    Returns:
        The scalar per-tick reward.
    """
    dev = cfg.w_E * abs(E - params.E_set) + cfg.w_T * abs(T - params.T_set) + cfg.w_R * abs(R - params.R_set)
    return 1.0 + cfg.w_serve * served - min(cfg.penalty_cap, dev)


def rollout(policy: MLPPolicy, params: PlantParams, ep_seed: int, cfg: EpisodeConfig) -> Tuple[float, int]:
    """Run one survival episode and return its total reward and lifetime.

    Args:
        policy: Policy under evaluation (closed loop).
        params: Plant parameters (a fresh copy is used; episodes never
            mutate the caller's instance).
        ep_seed: Episode seed; controls both the plant process noise and
            the perturbation schedule, so all candidates in a generation
            see identical conditions (common random numbers).
        cfg: Episode configuration.

    Returns:
        ``(total_reward, ticks_alive)``.
    """
    # The plant noise uses the global `random` stream (as in the CLI); the
    # perturbation schedule uses a dedicated RNG so the two are independent.
    random.seed(ep_seed)
    ev = random.Random(ep_seed * 7919 + 13)
    plant = Plant(params=replace(params), loop_engaged=True)

    sag_at, sag_end, sag_drop = -1, -1, 0.0
    if ev.random() < cfg.p_sag:
        sag_at = ev.randint(*cfg.sag_start)
        sag_end = sag_at + ev.randint(*cfg.sag_dur)
        sag_drop = ev.uniform(*cfg.sag_drop)
    flood_at, flood_end, flood_mult = -1, -1, 1.0
    if ev.random() < cfg.p_flood:
        flood_at = ev.randint(*cfg.flood_start)
        flood_end = flood_at + ev.randint(*cfg.flood_dur)
        flood_mult = ev.uniform(*cfg.flood_mult)

    total = 0.0
    ticks = 0
    for t in range(cfg.max_ticks):
        if t == sag_at:
            plant.apply_power_sag(sag_drop)
        elif t == sag_end:
            plant.set_power(plant.p.harvest_rate)
        if t == flood_at:
            plant.begin_ingress_flood(flood_mult)
        elif t == flood_end:
            plant.end_ingress_flood()

        state = plant.read_state()
        thr, cool, rep = policy.act(state)
        served = state["demand"] * (1.0 - plant.p.throttle_gain * thr)
        plant.step(Action(throttle=thr, cool=cool, repair=rep, accept_cmd=True))

        s = plant.s
        if s.E <= cfg.fail_E or s.T >= cfg.fail_T or s.R <= cfg.fail_R:
            break  # boundary failure: no reward for this tick, episode over
        total += _tick_reward(s.E, s.T, s.R, served, plant.p, cfg)
        ticks += 1
    return total, ticks


# --------------------------------------------------------------------------- #
# Evolution-strategy trainer
# --------------------------------------------------------------------------- #
def _episode_seeds(train_seed: int, gen: int, n_episodes: int) -> List[int]:
    """Deterministic per-generation episode seeds (shared across candidates)."""
    return [train_seed * 1_000_003 + gen * 1_000 + e for e in range(n_episodes)]


def evaluate(
    policy: MLPPolicy,
    vec: "np.ndarray",
    params: PlantParams,
    ep_seeds: List[int],
    cfg: EpisodeConfig,
) -> Tuple[float, float]:
    """Evaluate a parameter vector as mean episode reward over fixed seeds.

    Args:
        policy: Policy object used as the evaluation vehicle (its
            parameters are overwritten).
        vec: Flat parameter vector to evaluate.
        params: Plant parameters.
        ep_seeds: Episode seeds (common random numbers within a generation).
        cfg: Episode configuration.

    Returns:
        ``(mean_reward, mean_ticks_alive)``.
    """
    policy.set_vector(vec)
    rewards: List[float] = []
    lives: List[int] = []
    for s in ep_seeds:
        r, t = rollout(policy, params, s, cfg)
        rewards.append(r)
        lives.append(t)
    return float(np.mean(rewards)), float(np.mean(lives))


def _centered_ranks(f: "np.ndarray") -> "np.ndarray":
    """Map fitness values to centered ranks in ``[-0.5, 0.5]`` (ES utility)."""
    ranks = np.empty_like(f)
    ranks[np.argsort(f)] = np.arange(f.size, dtype=float)
    if f.size > 1:
        ranks = ranks / (f.size - 1) - 0.5
    else:
        ranks[...] = 0.0
    return ranks


def train(
    params: PlantParams,
    out_dir: str,
    generations: int = 60,
    pairs: int = 16,
    episodes: int = 3,
    sigma: float = 0.12,
    alpha: float = 0.20,
    hidden: int = 8,
    seed: int = 7,
    obs_keys: Tuple[str, ...] = INTEROCEPTIVE_OBS_KEYS,
    checkpoint_fracs: Tuple[float, ...] = DEFAULT_CHECKPOINT_FRACS,
    ep_cfg: Optional[EpisodeConfig] = None,
    config_label: str = "",
) -> Dict[str, Any]:
    """Train the policy with an antithetic ES and write checkpoints.

    Args:
        params: Plant parameters for the training environment.
        out_dir: Output directory (checkpoints under ``checkpoints/``).
        generations: Number of ES updates.
        pairs: Antithetic noise pairs per generation (population is
            ``2 * pairs``).
        episodes: Episodes per fitness evaluation.
        sigma: Noise standard deviation.
        alpha: Learning rate.
        hidden: Policy hidden-layer width.
        seed: Master seed (init, noise, and episode seeds derive from it).
        obs_keys: State channels the policy observes (the interoceptive
            ``(E, T, R)`` by default; the keys are stored in the
            checkpoint, so downstream consumers follow automatically).
        checkpoint_fracs: Training fractions at which to checkpoint.
        ep_cfg: Episode configuration (defaults to :class:`EpisodeConfig`).
        config_label: Label recorded in checkpoint metadata (e.g., the
            profile path the plant params came from).

    Returns:
        The training log payload (also written to ``training_log.json``).
    """
    cfg = ep_cfg or EpisodeConfig()
    rng = np.random.default_rng(seed)
    center = MLPPolicy(obs_keys=obs_keys, hidden=hidden, rng=rng)
    worker = MLPPolicy(obs_keys=obs_keys, hidden=hidden, rng=np.random.default_rng(0))
    theta = center.get_vector()
    n = theta.size

    ckpt_dir = os.path.join(out_dir, "checkpoints")
    os.makedirs(ckpt_dir, exist_ok=True)
    targets: Dict[int, float] = {int(round(f * generations)): f for f in sorted(set(checkpoint_fracs))}

    history: List[Dict[str, float]] = []
    checkpoints: List[Dict[str, Any]] = []
    t0 = time.time()
    for gen in range(generations + 1):
        ep_seeds = _episode_seeds(seed, gen, episodes)
        fit_c, life_c = evaluate(worker, theta, params, ep_seeds, cfg)

        if gen in targets:
            frac = targets[gen]
            name = f"ckpt_{int(round(100 * frac)):03d}.json"
            path = os.path.join(ckpt_dir, name)
            center.set_vector(theta)
            center.save(
                path,
                meta={
                    "frac": frac,
                    "generation": gen,
                    "fitness": round(fit_c, 3),
                    "ticks_alive": round(life_c, 1),
                    "train_seed": seed,
                    "config": config_label,
                },
            )
            checkpoints.append({"frac": frac, "generation": gen, "path": path, "fitness": round(fit_c, 3)})
            print(f"  checkpoint {name}: gen={gen} fitness={fit_c:.1f} ticks={life_c:.0f}", flush=True)
        if gen == generations:
            history.append({"gen": gen, "fitness": fit_c, "ticks_alive": life_c})
            break

        eps = rng.standard_normal((pairs, n))
        fits = np.empty(2 * pairs, dtype=float)
        for j in range(pairs):
            fits[2 * j], _ = evaluate(worker, theta + sigma * eps[j], params, ep_seeds, cfg)
            fits[2 * j + 1], _ = evaluate(worker, theta - sigma * eps[j], params, ep_seeds, cfg)
        util = _centered_ranks(fits)
        grad = np.zeros(n, dtype=float)
        for j in range(pairs):
            grad += (util[2 * j] - util[2 * j + 1]) * eps[j]
        grad /= 2.0 * pairs * sigma
        theta = theta + alpha * grad

        history.append(
            {
                "gen": gen,
                "fitness": fit_c,
                "ticks_alive": life_c,
                "pop_mean": float(np.mean(fits)),
                "pop_max": float(np.max(fits)),
            }
        )
        if gen % 5 == 0:
            print(
                f"  gen {gen:3d}: fitness={fit_c:7.1f} ticks={life_c:5.0f} "
                f"pop_mean={np.mean(fits):7.1f} pop_max={np.max(fits):7.1f}",
                flush=True,
            )

    log: Dict[str, Any] = {
        "seed": seed,
        "generations": generations,
        "pairs": pairs,
        "episodes": episodes,
        "sigma": sigma,
        "alpha": alpha,
        "hidden": hidden,
        "obs_keys": list(obs_keys),
        "n_params": int(n),
        "episode_config": asdict(cfg),
        "config_label": config_label,
        "elapsed_sec": round(time.time() - t0, 1),
        "checkpoints": checkpoints,
        "history": history,
    }
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "training_log.json"), "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2)
    return log


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def plant_params_from_profile(path: str) -> PlantParams:
    """Build :class:`PlantParams` from a profile's ``plant.params`` block."""
    with open(path, "r", encoding="utf-8") as f:
        prof = dict(yaml.safe_load(f) or {})
    overrides = (prof.get("plant", {}) or {}).get("params", {}) or {}
    valid = set(PlantParams().__dict__.keys())
    clean = {k: v for k, v in overrides.items() if k in valid}
    return PlantParams(**clean) if clean else PlantParams()


def main() -> None:
    """CLI entry point for policy training."""
    ap = argparse.ArgumentParser(description="Train the emergence policy (pure-NumPy ES) and write checkpoints.")
    ap.add_argument("--config", type=str, default=os.path.join(REPO_ROOT, "configs", "profile_emergence.yml"))
    ap.add_argument("--out", type=str, default=os.path.join(REPO_ROOT, "artifacts", "emergence"))
    ap.add_argument("--generations", type=int, default=600)
    ap.add_argument("--pairs", type=int, default=16, help="Antithetic noise pairs (population = 2*pairs).")
    ap.add_argument("--episodes", type=int, default=6, help="Episodes per fitness evaluation.")
    ap.add_argument("--sigma", type=float, default=0.15)
    ap.add_argument("--alpha", type=float, default=0.25)
    ap.add_argument("--hidden", type=int, default=8)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument(
        "--obs",
        type=str,
        default=",".join(INTEROCEPTIVE_OBS_KEYS),
        help="Comma-separated state channels the policy observes (interoceptive E,T,R by default).",
    )
    ap.add_argument(
        "--checkpoints",
        type=str,
        default=",".join(str(f) for f in DEFAULT_CHECKPOINT_FRACS),
        help="Comma-separated training fractions at which to checkpoint.",
    )
    args = ap.parse_args()

    params = plant_params_from_profile(args.config)
    fracs = tuple(float(s) for s in args.checkpoints.split(",") if s.strip())
    obs_keys = tuple(s.strip() for s in args.obs.split(",") if s.strip())
    print(
        f"Training: {args.generations} generations x {2 * args.pairs} candidates x "
        f"{args.episodes} episodes (seed={args.seed}, obs={','.join(obs_keys)}) -> {args.out}",
        flush=True,
    )
    log = train(
        params=params,
        out_dir=args.out,
        generations=args.generations,
        pairs=args.pairs,
        episodes=args.episodes,
        sigma=args.sigma,
        alpha=args.alpha,
        hidden=args.hidden,
        seed=args.seed,
        obs_keys=obs_keys,
        checkpoint_fracs=fracs,
        config_label=os.path.relpath(args.config, REPO_ROOT),
    )
    final = log["history"][-1]
    print(f"Done in {log['elapsed_sec']}s. Final fitness={final['fitness']:.1f} ticks={final['ticks_alive']:.0f}")
    print(f"Wrote: {os.path.join(args.out, 'training_log.json')}")


if __name__ == "__main__":
    main()
