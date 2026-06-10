"""Learned-policy controller for the software plant.

This module is the policy-driven counterpart of the hand-coded
[`ControllerPolicy`][ldtc.arbiter.policy.ControllerPolicy]. It provides a
tiny pure-NumPy multilayer perceptron
([`MLPPolicy`][ldtc.plant.policy_controller.MLPPolicy]) that maps the
observed plant state to actuator settings, and a
[`PolicyController`][ldtc.plant.policy_controller.PolicyController]
adapter that lets the verification harness drive the plant with a trained
checkpoint, or with a matched state-independent ablation of one.

The point of the learned controller is the emergence-under-learning
demonstration: nothing in the policy is hand-wired to couple the internal
nodes to one another. The policy is trained (see ``scripts/train_agent.py``)
with a survival, service, and homeostasis reward (no term mentions loop
dominance or the estimator) on a plant whose intrinsic cross-couplings
are zeroed, so any loop dominance the harness measures must be carried by
the *learned* state-to-actuation pathway rather than by designed coupling.
The ablations close the argument: replaying the trained policy's own
action statistics without their state dependence (``shuffled``) or holding
its mean action (``frozen``) preserves the actuation marginals while
severing the closed loop, so measured dominance must collapse if it was
genuinely loop-carried.

Checkpoints are stored as plain JSON (weights as nested lists plus
metadata), so no learning-framework dependency is required to train,
store, or replay a policy.

See Also:
    `scripts/train_agent.py`: evolution-strategy training loop.
    `scripts/emergence.py`: checkpoint sweep through the production harness.
    `paper/main.tex`: Results (loop dominance emerges under learning).
"""

from __future__ import annotations

import json
import os
import random
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple

import numpy as np

from .models import Action

# Default observation vector, in order: the full observed state. The class
# is observation-agnostic (any subset of state keys, recorded in the
# checkpoint); the emergence training restricts it to the interoceptive
# internal nodes (E, T, R) so the learned law is internal-state feedback
# (see scripts/train_agent.py).
DEFAULT_OBS_KEYS: Tuple[str, ...] = ("E", "T", "R", "demand", "io", "H")

# Supported ablation modes for `PolicyController`.
ABLATION_MODES: Tuple[str, ...] = ("none", "shuffled", "frozen")


def _sigmoid(z: "np.ndarray") -> "np.ndarray":
    """Numerically stable logistic function."""
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30.0, 30.0)))


class MLPPolicy:
    """Tiny dependency-light MLP policy: observed state -> actuator settings.

    One hidden tanh layer and a sigmoid output head, implemented directly
    in NumPy so the core package needs no learning framework. Outputs are
    the three actuator commands ``(throttle, cool, repair)``, each in
    ``[0, 1]``.

    The parameters are exposed as a single flat vector
    ([`get_vector`][ldtc.plant.policy_controller.MLPPolicy.get_vector] /
    [`set_vector`][ldtc.plant.policy_controller.MLPPolicy.set_vector]) so a
    black-box trainer (e.g., an evolution strategy) can optimize the policy
    without touching its internals.

    Args:
        obs_keys: Ordered state keys forming the observation vector.
        hidden: Hidden-layer width.
        init_scale: Standard deviation of the Gaussian weight init.
        rng: NumPy generator used for the init (defaults to a fixed seed
            so an unconfigured policy is reproducible).
    """

    N_ACTIONS: int = 3

    def __init__(
        self,
        obs_keys: Sequence[str] = DEFAULT_OBS_KEYS,
        hidden: int = 8,
        init_scale: float = 0.1,
        rng: Optional[np.random.Generator] = None,
    ) -> None:
        """Initialize a randomly seeded policy (see class docstring)."""
        if hidden < 1:
            raise ValueError("hidden must be >= 1")
        self.obs_keys: Tuple[str, ...] = tuple(str(k) for k in obs_keys)
        self.hidden = int(hidden)
        #: Checkpoint metadata (populated by `save` / `load`).
        self.meta: Dict[str, Any] = {}
        g = rng if rng is not None else np.random.default_rng(0)
        n_in = len(self.obs_keys)
        scale = float(init_scale)
        self.W1 = scale * g.standard_normal((self.hidden, n_in))
        self.b1 = scale * g.standard_normal(self.hidden)
        self.W2 = scale * g.standard_normal((self.N_ACTIONS, self.hidden))
        self.b2 = scale * g.standard_normal(self.N_ACTIONS)

    # ------------------------------------------------------------------ #
    # Flat-vector parameter access (for black-box trainers)
    # ------------------------------------------------------------------ #
    @property
    def n_params(self) -> int:
        """Total number of trainable parameters."""
        return int(self.W1.size + self.b1.size + self.W2.size + self.b2.size)

    def get_vector(self) -> "np.ndarray":
        """Return all parameters concatenated into one flat float vector."""
        return np.concatenate([self.W1.ravel(), self.b1.ravel(), self.W2.ravel(), self.b2.ravel()]).astype(float)

    def set_vector(self, vec: "np.ndarray") -> None:
        """Load all parameters from one flat vector.

        Args:
            vec: Flat parameter vector of length
                [`n_params`][ldtc.plant.policy_controller.MLPPolicy.n_params].

        Raises:
            ValueError: If ``vec`` has the wrong length.
        """
        v = np.asarray(vec, dtype=float).ravel()
        if v.size != self.n_params:
            raise ValueError(f"Expected {self.n_params} params, got {v.size}")
        i = 0
        for arr in (self.W1, self.b1, self.W2, self.b2):
            arr[...] = v[i : i + arr.size].reshape(arr.shape)
            i += arr.size

    # ------------------------------------------------------------------ #
    # Acting
    # ------------------------------------------------------------------ #
    def act(self, state: Dict[str, float]) -> Tuple[float, float, float]:
        """Compute actuator settings for one observed state.

        Observations are affinely rescaled from their native ``[0, 1]``
        range to ``[-1, 1]`` (a fixed architecture constant, independent of
        the plant's setpoints) so the network operates around zero.

        Args:
            state: Plant state dict (missing keys read as ``0.0``).

        Returns:
            ``(throttle, cool, repair)``, each clipped to ``[0, 1]`` by the
            sigmoid output head.
        """
        x = np.asarray([2.0 * float(state.get(k, 0.0)) - 1.0 for k in self.obs_keys], dtype=float)
        h = np.tanh(self.W1 @ x + self.b1)
        y = _sigmoid(self.W2 @ h + self.b2)
        return (float(y[0]), float(y[1]), float(y[2]))

    # ------------------------------------------------------------------ #
    # JSON checkpoint I/O
    # ------------------------------------------------------------------ #
    def save(self, path: str, meta: Optional[Dict[str, Any]] = None) -> None:
        """Write the policy (weights plus metadata) as a JSON checkpoint.

        Args:
            path: Destination file path (parent directories are created).
            meta: Optional metadata recorded under the ``meta`` key (e.g.,
                training fraction, generation, fitness, seed).
        """
        payload: Dict[str, Any] = {
            "kind": "ldtc_policy",
            "version": 1,
            "obs_keys": list(self.obs_keys),
            "hidden": self.hidden,
            "W1": self.W1.tolist(),
            "b1": self.b1.tolist(),
            "W2": self.W2.tolist(),
            "b2": self.b2.tolist(),
            "meta": dict(meta or {}),
        }
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        self.meta = dict(meta or {})

    @classmethod
    def load(cls, path: str) -> "MLPPolicy":
        """Load a policy from a JSON checkpoint written by ``save``.

        Args:
            path: Checkpoint file path.

        Returns:
            The reconstructed policy; its ``meta`` attribute holds the
            checkpoint metadata.

        Raises:
            ValueError: If the file is not an LDTC policy checkpoint.
        """
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if payload.get("kind") != "ldtc_policy":
            raise ValueError(f"Not an LDTC policy checkpoint: {path}")
        pol = cls(obs_keys=payload["obs_keys"], hidden=int(payload["hidden"]))
        pol.W1 = np.asarray(payload["W1"], dtype=float)
        pol.b1 = np.asarray(payload["b1"], dtype=float)
        pol.W2 = np.asarray(payload["W2"], dtype=float)
        pol.b2 = np.asarray(payload["b2"], dtype=float)
        pol.meta = dict(payload.get("meta", {}))
        return pol


class _AdapterLike(Protocol):
    """Minimal adapter surface tape recording needs (read + actuate)."""

    def read_state(self) -> Dict[str, float]:
        """Return the latest plant state as a dict of named floats."""
        ...

    def write_actuators(self, action: Action) -> None:
        """Send actuator commands to the plant."""
        ...


def record_policy_tape(adapter: _AdapterLike, policy: MLPPolicy, ticks: int) -> List[Tuple[float, float, float]]:
    """Record the action trace of a closed-loop policy rollout.

    Drives ``adapter`` with ``policy`` for ``ticks`` steps on a throwaway
    plant instance and returns the action sequence. The tape supplies the
    matched action statistics for the ``shuffled`` and ``frozen`` ablations
    of [`PolicyController`][ldtc.plant.policy_controller.PolicyController]:
    only the tape crosses into the measured run.

    Args:
        adapter: Fresh plant adapter to drive (built from the same profile
            as the measured run).
        policy: Trained policy under ablation.
        ticks: Number of actions to record.

    Returns:
        List of ``ticks`` recorded ``(throttle, cool, repair)`` tuples.
    """
    tape: List[Tuple[float, float, float]] = []
    for _ in range(int(ticks)):
        state = adapter.read_state()
        a = policy.act(state)
        adapter.write_actuators(Action(throttle=a[0], cool=a[1], repair=a[2], accept_cmd=True))
        tape.append(a)
    return tape


class PolicyController:
    """Drive the plant with a learned policy, or a matched ablation of it.

    The controller mirrors the role of the hand-coded
    [`ControllerPolicy`][ldtc.arbiter.policy.ControllerPolicy] in the
    verification loop: each tick it turns the observed state into a plant
    [`Action`][ldtc.plant.models.Action]. Three modes are supported:

    - ``"none"``: the policy acts on the current state (the closed loop
      under test).
    - ``"shuffled"``: actions are drawn i.i.d. (seeded) from a recorded
      tape of the same policy's closed-loop behavior, so the marginal
      action statistics match while every action is independent of the
      current state.
    - ``"frozen"``: the tape's mean action is held constant.

    Args:
        policy: Trained policy checkpoint.
        ablation: One of ``"none"``, ``"shuffled"``, ``"frozen"``.
        tape: Recorded action tuples from
            [`record_policy_tape`][ldtc.plant.policy_controller.record_policy_tape]
            (required for the ablation modes).
        seed: Seed for the dedicated ablation RNG (kept separate from the
            global stream so the plant noise is unaffected).

    Raises:
        ValueError: If ``ablation`` is unknown, or an ablation mode is
            requested without a non-empty tape.
    """

    def __init__(
        self,
        policy: MLPPolicy,
        ablation: str = "none",
        tape: Optional[List[Tuple[float, float, float]]] = None,
        seed: int = 0,
    ) -> None:
        """Initialize the controller (see class docstring)."""
        if ablation not in ABLATION_MODES:
            raise ValueError(f"Unknown ablation mode: {ablation} (expected one of {ABLATION_MODES})")
        if ablation != "none" and not tape:
            raise ValueError(f"Ablation mode '{ablation}' requires a non-empty action tape")
        self.policy = policy
        self.ablation = ablation
        self._tape = list(tape or [])
        self._rng = random.Random(int(seed))
        if self._tape:
            arr = np.asarray(self._tape, dtype=float)
            self._frozen: Tuple[float, float, float] = (
                float(arr[:, 0].mean()),
                float(arr[:, 1].mean()),
                float(arr[:, 2].mean()),
            )
        else:
            self._frozen = (0.0, 0.0, 0.0)

    def compute(self, state: Dict[str, float]) -> Action:
        """Compute the actuator action for one tick.

        Args:
            state: Observed plant state.

        Returns:
            Plant [`Action`][ldtc.plant.models.Action] for this tick.
            External commands are always accepted (`accept_cmd=True`); the
            refusal arbiter is not part of the learned-policy scenario.
        """
        if self.ablation == "shuffled":
            a = self._tape[self._rng.randrange(len(self._tape))]
        elif self.ablation == "frozen":
            a = self._frozen
        else:
            a = self.policy.act(state)
        return Action(throttle=a[0], cool=a[1], repair=a[2], accept_cmd=True)
