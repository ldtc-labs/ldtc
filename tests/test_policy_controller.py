"""Tests: learned-policy controller and emergence training pieces.

Covers the pure-NumPy MLP policy (parameter vector round trip, JSON
checkpoint I/O, bounded outputs), the matched state-independent ablations
of `PolicyController` (shuffled and frozen), the action-tape recorder, the
training-environment reward shaping and rollout determinism, and a fast
end-to-end smoke run of the `run-policy` CLI handler.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys

import numpy as np
import pytest
import yaml

from ldtc.plant.adapter import PlantAdapter
from ldtc.plant.models import Plant, PlantParams
from ldtc.plant.policy_controller import (
    ABLATION_MODES,
    MLPPolicy,
    PolicyController,
    record_policy_tape,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))


# --------------------------------------------------------------------------- #
# MLPPolicy
# --------------------------------------------------------------------------- #
def test_policy_outputs_are_actuator_bounded():
    pol = MLPPolicy(rng=np.random.default_rng(3))
    for state in (
        {"E": 0.0, "T": 0.0, "R": 0.0, "demand": 0.0, "io": 0.0, "H": 0.0},
        {"E": 1.0, "T": 1.0, "R": 1.0, "demand": 1.0, "io": 1.0, "H": 1.0},
        {"E": 0.6, "T": 0.35, "R": 0.85, "demand": 0.5, "io": 0.3, "H": 0.02},
        {},  # missing keys read as 0.0
    ):
        a = pol.act(state)
        assert len(a) == 3
        assert all(0.0 <= v <= 1.0 for v in a)


def test_policy_vector_round_trip_changes_and_restores_behavior():
    pol = MLPPolicy(rng=np.random.default_rng(5))
    state = {"E": 0.6, "T": 0.35, "R": 0.85, "demand": 0.5, "io": 0.3, "H": 0.02}
    vec = pol.get_vector()
    assert vec.size == pol.n_params
    a0 = pol.act(state)
    pol.set_vector(vec + 0.5)
    assert pol.act(state) != a0
    pol.set_vector(vec)
    assert pol.act(state) == pytest.approx(a0)


def test_policy_vector_wrong_length_rejected():
    pol = MLPPolicy()
    with pytest.raises(ValueError):
        pol.set_vector(np.zeros(pol.n_params - 1))


def test_policy_checkpoint_round_trip(tmp_path):
    pol = MLPPolicy(rng=np.random.default_rng(11))
    path = str(tmp_path / "ckpt.json")
    pol.save(path, meta={"frac": 0.5, "generation": 30})
    loaded = MLPPolicy.load(path)
    state = {"E": 0.5, "T": 0.4, "R": 0.8, "demand": 0.6, "io": 0.2, "H": 0.02}
    assert loaded.act(state) == pytest.approx(pol.act(state))
    assert loaded.meta["frac"] == 0.5
    assert loaded.meta["generation"] == 30


def test_policy_checkpoint_rejects_foreign_json(tmp_path):
    path = str(tmp_path / "not_a_policy.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"kind": "something_else"}, f)
    with pytest.raises(ValueError):
        MLPPolicy.load(path)


def test_policy_meta_is_per_instance():
    a = MLPPolicy()
    b = MLPPolicy()
    a.meta["frac"] = 1.0
    assert "frac" not in b.meta


# --------------------------------------------------------------------------- #
# PolicyController and ablations
# --------------------------------------------------------------------------- #
def _tape(n=50, seed=7):
    random.seed(seed)
    adapter = PlantAdapter(Plant(params=PlantParams()))
    pol = MLPPolicy(rng=np.random.default_rng(seed))
    return pol, record_policy_tape(adapter, pol, n)


def test_record_policy_tape_length_and_bounds():
    _, tape = _tape(n=30)
    assert len(tape) == 30
    assert all(0.0 <= v <= 1.0 for a in tape for v in a)


def test_controller_none_mode_tracks_state():
    pol, _ = _tape()
    ctrl = PolicyController(pol, ablation="none")
    s1 = {"E": 0.2, "T": 0.9, "R": 0.3, "demand": 0.5, "io": 0.3, "H": 0.02}
    s2 = {"E": 0.9, "T": 0.1, "R": 0.95, "demand": 0.5, "io": 0.3, "H": 0.02}
    a1, a2 = ctrl.compute(s1), ctrl.compute(s2)
    assert (a1.throttle, a1.cool, a1.repair) != (a2.throttle, a2.cool, a2.repair)


def test_shuffled_ablation_is_state_independent_and_tape_marginal():
    pol, tape = _tape()
    ctrl_a = PolicyController(pol, ablation="shuffled", tape=tape, seed=123)
    ctrl_b = PolicyController(pol, ablation="shuffled", tape=tape, seed=123)
    sa = {"E": 0.1, "T": 0.95, "R": 0.2, "demand": 0.9, "io": 0.8, "H": 0.0}
    sb = {"E": 0.9, "T": 0.05, "R": 0.99, "demand": 0.1, "io": 0.1, "H": 0.05}
    tape_set = set(tape)
    for _ in range(20):
        aa, ab = ctrl_a.compute(sa), ctrl_b.compute(sb)
        # Same seed, wildly different states: identical action stream.
        assert (aa.throttle, aa.cool, aa.repair) == (ab.throttle, ab.cool, ab.repair)
        # Every action is drawn from the recorded tape (matched marginals).
        assert (aa.throttle, aa.cool, aa.repair) in tape_set


def test_frozen_ablation_holds_tape_mean():
    pol, tape = _tape()
    ctrl = PolicyController(pol, ablation="frozen", tape=tape)
    arr = np.asarray(tape, dtype=float)
    expect = (arr[:, 0].mean(), arr[:, 1].mean(), arr[:, 2].mean())
    for state in ({"E": 0.1}, {"E": 0.9, "T": 0.9}):
        a = ctrl.compute(state)
        assert (a.throttle, a.cool, a.repair) == pytest.approx(expect)


def test_ablation_modes_require_tape_and_known_name():
    pol, tape = _tape()
    assert ABLATION_MODES == ("none", "shuffled", "frozen")
    with pytest.raises(ValueError):
        PolicyController(pol, ablation="shuffled", tape=None)
    with pytest.raises(ValueError):
        PolicyController(pol, ablation="nope", tape=tape)


# --------------------------------------------------------------------------- #
# Training environment (scripts/train_agent.py)
# --------------------------------------------------------------------------- #
def test_rollout_is_deterministic_given_seed():
    from train_agent import EpisodeConfig, plant_params_from_profile, rollout

    params = plant_params_from_profile(os.path.join(REPO_ROOT, "configs", "profile_emergence.yml"))
    pol = MLPPolicy(rng=np.random.default_rng(2))
    cfg = EpisodeConfig(max_ticks=120)
    r1 = rollout(pol, params, ep_seed=42, cfg=cfg)
    r2 = rollout(pol, params, ep_seed=42, cfg=cfg)
    assert r1 == r2
    assert 0 < r1[1] <= 120


def test_tick_reward_prefers_setpoints_and_service():
    from train_agent import EpisodeConfig, _tick_reward, plant_params_from_profile

    params = plant_params_from_profile(os.path.join(REPO_ROOT, "configs", "profile_emergence.yml"))
    cfg = EpisodeConfig()
    at_set = _tick_reward(params.E_set, params.T_set, params.R_set, 0.5, params, cfg)
    off_set = _tick_reward(params.E_set, params.T_set + 0.2, params.R_set, 0.5, params, cfg)
    unserved = _tick_reward(params.E_set, params.T_set, params.R_set, 0.0, params, cfg)
    assert at_set > off_set
    assert at_set > unserved
    # The penalty cap keeps every surviving tick worth more than death.
    worst = _tick_reward(0.0, 1.0, 0.0, 0.0, params, cfg)
    assert worst > 0.0


def test_es_training_smoke_improves_and_checkpoints(tmp_path):
    from train_agent import EpisodeConfig, plant_params_from_profile, train

    params = plant_params_from_profile(os.path.join(REPO_ROOT, "configs", "profile_emergence.yml"))
    cfg = EpisodeConfig(max_ticks=60)
    log = train(
        params=params,
        out_dir=str(tmp_path),
        generations=4,
        pairs=3,
        episodes=1,
        seed=5,
        checkpoint_fracs=(0.0, 1.0),
        ep_cfg=cfg,
    )
    names = sorted(os.listdir(tmp_path / "checkpoints"))
    assert names == ["ckpt_000.json", "ckpt_100.json"]
    assert len(log["history"]) == 5
    assert os.path.exists(tmp_path / "training_log.json")
    # Checkpoints are loadable policies.
    pol = MLPPolicy.load(str(tmp_path / "checkpoints" / "ckpt_100.json"))
    assert pol.meta["frac"] == 1.0


# --------------------------------------------------------------------------- #
# Emergence sweep utilities (scripts/emergence.py)
# --------------------------------------------------------------------------- #
def test_discover_checkpoints_sorts_by_frac(tmp_path):
    from emergence import condition_name, discover_checkpoints

    ck = tmp_path / "checkpoints"
    ck.mkdir()
    for frac, gen in ((1.0, 40), (0.0, 0), (0.25, 10)):
        MLPPolicy().save(str(ck / f"ckpt_{int(100 * frac):03d}.json"), meta={"frac": frac, "generation": gen})
    found = discover_checkpoints(str(ck))
    assert [c["frac"] for c in found] == [0.0, 0.25, 1.0]
    assert [c["generation"] for c in found] == [0, 10, 40]
    assert condition_name(0.25) == "frac_025"
    assert condition_name(1.0, "frozen") == "ablate_frozen"
    with pytest.raises(FileNotFoundError):
        discover_checkpoints(str(tmp_path / "missing"))


# --------------------------------------------------------------------------- #
# CLI handler smoke (run-policy, all ablation modes)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("ablation", ["none", "shuffled", "frozen"])
def test_run_policy_cli_smoke(tmp_path, monkeypatch, capsys, ablation):
    from ldtc.cli import main as cli

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LDTC_SKIP_REPORT", "1")

    with open(os.path.join(REPO_ROOT, "configs", "profile_emergence.yml"), "r", encoding="utf-8") as f:
        prof = dict(yaml.safe_load(f))
    prof["baseline_sec"] = 6.0
    prof["diag_cadence_windows"] = 1000
    cfg_path = str(tmp_path / "prof.yml")
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(prof, f)

    ckpt = str(tmp_path / "ckpt.json")
    MLPPolicy(rng=np.random.default_rng(9)).save(ckpt, meta={"frac": 1.0, "generation": 1})

    cli.run_policy(argparse.Namespace(config=cfg_path, policy=ckpt, ablation=ablation))
    out = capsys.readouterr().out
    assert "Policy run done" in out

    runs = [d for d in os.listdir(tmp_path / "artifacts" / "runs")]
    assert len(runs) == 1
    audit = tmp_path / "artifacts" / "runs" / runs[0] / "audits" / "audit.jsonl"
    events = [json.loads(line).get("event") for line in open(audit, encoding="utf-8")]
    assert "policy_loaded" in events
    if ablation != "none":
        assert "policy_tape_recorded" in events
