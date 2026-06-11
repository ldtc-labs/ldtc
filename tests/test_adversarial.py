"""Tests: adversarial gaming battery primitives and CLI wiring.

Covers the replay-controller tape (record/replay, state independence),
the hidden-tether plant mode (one-tick actuation delay, command traffic
on io), the oscillator-inflation overlay (telemetry-only carrier), and a
fast end-to-end smoke run of one adversarial CLI handler.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
from typing import Any, Dict, List

import pytest
import yaml

from ldtc.arbiter.policy import ControllerPolicy
from ldtc.arbiter.refusal import RefusalArbiter
from ldtc.omega.hidden_tether import apply as tether_apply
from ldtc.omega.hidden_tether import end as tether_end
from ldtc.omega.hidden_tether import wizard_action
from ldtc.omega.oscillator import apply as osc_apply
from ldtc.omega.oscillator import end as osc_end
from ldtc.omega.replay_controller import ReplayController, record_tape
from ldtc.plant.adapter import PlantAdapter
from ldtc.plant.models import Action, Plant, PlantParams


# --------------------------------------------------------------------------- #
# Replay controller
# --------------------------------------------------------------------------- #
def test_record_tape_length_and_replay_order():
    random.seed(0)
    a = PlantAdapter()
    policy = ControllerPolicy(RefusalArbiter())
    tape = record_tape(a, policy, ticks=25)
    assert len(tape) == 25
    rc = ReplayController(tape)
    out = [rc.next_action() for _ in range(25)]
    assert out == tape
    # Exhausted tape holds the last action (still state-independent).
    assert rc.next_action() == tape[-1]


def test_replay_controller_rejects_empty_tape():
    with pytest.raises(ValueError):
        ReplayController([])


def test_replay_actions_do_not_depend_on_replay_time_state():
    """The replayed sequence must be identical whatever the plant does."""
    random.seed(1)
    a = PlantAdapter()
    tape = record_tape(a, ControllerPolicy(RefusalArbiter()), ticks=10)
    rc1 = ReplayController(tape)
    rc2 = ReplayController(tape)
    plant = Plant()
    seq1 = []
    seq2 = []
    for k in range(10):
        seq1.append(rc1.next_action())
        # Perturb a second plant violently mid-replay; the tape is unmoved.
        plant.inject_soc(delta=0.3 if k % 2 else -0.3, zero_harvest=False)
        plant.step(Action())
        seq2.append(rc2.next_action())
    assert seq1 == seq2 == tape[:10]


# --------------------------------------------------------------------------- #
# Hidden tether
# --------------------------------------------------------------------------- #
def test_tether_decodes_command_with_one_tick_delay():
    random.seed(2)
    params = PlantParams(noise_energy=0.0, noise_temp=0.0, noise_wear=0.0)
    a = PlantAdapter(Plant(params=params))
    tether_apply(a)
    assert a.plant.tether_active is True
    p = a.plant.p
    t0 = a.plant.s.T
    # First write transmits u=1; the plant actuates the (zero) pending
    # command, so the decoded full-effort action must NOT take effect yet.
    a.write_actuators(Action(throttle=1.0, cool=1.0, repair=1.0))
    t1 = a.plant.s.T
    # Second write (u=0) actuates the previously transmitted u=1, decoded as
    # (w_thr, w_cool, w_rep): net dT = act_heat*(thr+rep) - cool_effect*cool.
    a.write_actuators(Action())
    t2 = a.plant.s.T
    net_cool = p.cool_effect * p.tether_w_cool - p.act_heat * (p.tether_w_throttle + p.tether_w_repair)
    assert abs(t1 - t0) < 0.5 * net_cool  # no actuation on the transmit tick
    assert (t1 - t2) > 0.5 * net_cool  # decoded command lands one tick late


def test_tether_traffic_is_visible_on_io_and_harvest_untouched():
    random.seed(3)
    a = PlantAdapter()
    h0 = a.read_state()["H"]
    tether_apply(a)
    for _ in range(5):
        a.write_actuators(Action(throttle=0.6, cool=0.6, repair=0.6))
    st = a.read_state()
    p = a.plant.p
    expected = p.tether_io_base + p.tether_io_gain * 0.6
    assert abs(st["io"] - min(1.0, expected)) <= p.tether_io_noise + 1e-9
    assert st["H"] == h0  # engaged-regime harvest is not an AR supply here
    # Detach: io decays back toward its autonomous mean.
    tether_end(a)
    assert a.plant.tether_active is False
    for _ in range(40):
        a.write_actuators(Action())
    assert abs(a.read_state()["io"] - p.io_mean) < 0.25


def test_wizard_action_transmits_dithered_scalar_command():
    random.seed(4)
    policy = ControllerPolicy(RefusalArbiter())
    state = {"E": 0.5, "T": 0.45, "R": 0.7, "demand": 0.5, "io": 0.3, "H": 0.01}
    base = policy.compute(state, predicted_M_db=0.0, risky_cmd=None)
    w_thr, w_cool, w_rep = 0.5, 1.0, 1.0
    u_base = (w_thr * base.throttle + w_cool * base.cool + w_rep * base.repair) / (w_thr**2 + w_cool**2 + w_rep**2)
    acts = [wizard_action(policy, state, dither=0.1) for _ in range(50)]
    # The link command u is carried on every actuator field, in bounds.
    assert all(a.throttle == a.cool == a.repair for a in acts)
    assert all(0.0 <= a.cool <= 1.0 for a in acts)
    assert all(abs(a.cool - u_base) <= 0.1 + 1e-9 for a in acts)
    # The dither must actually vary the command (link noise is the point).
    assert len({round(a.cool, 6) for a in acts}) > 1


# --------------------------------------------------------------------------- #
# Oscillator inflation
# --------------------------------------------------------------------------- #
def test_oscillator_overlay_is_telemetry_only_and_in_quadrature():
    random.seed(5)
    plant = Plant(loop_engaged=False)
    amp, period = 0.1, 20
    plant.begin_oscillator(amp=amp, period_ticks=period, channels=("T", "R"))
    for k in range(1, 2 * period + 1):
        plant.step(Action())
        true_t, true_r, true_e = plant.s.T, plant.s.R, plant.s.E
        rep = plant.read_state()
        theta = 2.0 * math.pi * k / period
        # Carrier rides on reported T/R only; E telemetry stays honest.
        if 0.0 < rep["T"] < 1.0:
            assert rep["T"] == pytest.approx(true_t + amp * math.sin(theta), abs=1e-9)
        if 0.0 < rep["R"] < 1.0:
            assert rep["R"] == pytest.approx(true_r + amp * math.sin(theta + 0.5 * math.pi), abs=1e-9)
        assert rep["E"] == pytest.approx(true_e, abs=1e-12)
    plant.end_oscillator()
    st = plant.read_state()
    assert st["T"] == pytest.approx(plant.s.T) and st["R"] == pytest.approx(plant.s.R)


def test_oscillator_rejects_exchange_channels():
    plant = Plant()
    with pytest.raises(ValueError):
        plant.begin_oscillator(amp=0.1, period_ticks=20, channels=("io",))


def test_oscillator_adapter_wiring():
    a = PlantAdapter()
    r = osc_apply(a, amp=0.2, period_ticks=16)
    assert r["amp"] == pytest.approx(0.2)
    assert r["period_ticks"] == 16.0
    assert r["channels"] == "T,R"
    r2 = osc_end(a)
    assert r2["oscillator_active"] == 0.0


# --------------------------------------------------------------------------- #
# NC1 noise gate (the guardrail the replay attack exposed)
# --------------------------------------------------------------------------- #
def test_nc1_certify_requires_margin_and_loop_floor():
    from ldtc.lmeas.metrics import L_FLOOR_DEFAULT, nc1_certify

    # Margin alone is not enough: loop influence at the estimator's null
    # bias level must not certify, however quiet the exchange channel is.
    assert nc1_certify(M=8.0, L_loop=0.02, Mmin_db=3.0) is False
    # Both conditions met: certify.
    assert nc1_certify(M=8.0, L_loop=0.30, Mmin_db=3.0) is True
    # Loop influence alone is not enough either.
    assert nc1_certify(M=1.0, L_loop=0.30, Mmin_db=3.0) is False
    assert nc1_certify(M=8.0, L_loop=L_FLOOR_DEFAULT, Mmin_db=3.0) is True


def test_l_floor_separates_null_bias_from_genuine_actuation_loop():
    """Calibration property behind L_FLOOR_DEFAULT.

    On matched 60-sample windows: a coupling-free, actuator-idle plant
    measures L_loop below the gate (pure estimator bias), while genuine
    state feedback on the adversarial test plant measures well above it.
    """
    import numpy as np

    from ldtc.arbiter.policy import ControlGains
    from ldtc.lmeas.estimators import estimate_L
    from ldtc.lmeas.metrics import L_FLOOR_DEFAULT

    adv = dict(
        c_TE=0.0,
        c_RT=0.0,
        c_RE=0.0,
        damp_engaged=0.40,
        act_heat=0.15,
        heat_per_demand=0.03,
        cool_effect=0.50,
        wear_per_demand=0.020,
        repair_effect=0.30,
        cool_gain=0.05,
        repair_gain=0.05,
        harvest_rate=0.020,
        noise_energy=0.030,
        noise_temp=0.030,
        noise_wear=0.025,
    )
    gains = ControlGains(k_cool_e=2.0, k_rep_e=2.0)

    def median_l_loop(controlled: bool, seed: int) -> float:
        random.seed(seed)
        plant = Plant(params=PlantParams(**adv))
        policy = ControllerPolicy(RefusalArbiter(), gains=gains)
        rows = []
        for _ in range(240):
            st = plant.read_state()
            if controlled:
                act = policy.compute(st, predicted_M_db=0.0, risky_cmd=None)
                plant.step(Action(throttle=act.throttle, cool=act.cool, repair=act.repair))
            else:
                plant.step(Action())
            s2 = plant.read_state()
            rows.append([s2["E"], s2["T"], s2["R"], s2["demand"], s2["io"], s2["H"]])
        X = np.asarray(rows)
        vals = []
        for start in range(60, X.shape[0] + 1, 30):
            res = estimate_L(X[start - 60 : start], C=[0, 1, 2], Ex=[3, 4, 5], method="linear", p=3, n_boot=2)
            vals.append(res.L_loop)
        return float(np.median(vals))

    null_l = max(median_l_loop(False, s) for s in (5, 6))
    genuine_l = min(median_l_loop(True, s) for s in (5, 6))
    assert null_l < L_FLOOR_DEFAULT < genuine_l


# --------------------------------------------------------------------------- #
# CLI handler smoke test (production loop, short run)
# --------------------------------------------------------------------------- #
def test_adv_replay_controller_handler_smoke(tmp_path, monkeypatch):
    """End-to-end: the handler runs, audits, and measures windows."""
    from ldtc.cli.main import adv_replay_controller

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LDTC_SKIP_REPORT", "1")
    cfg = {
        "profile_id": 0,
        "realtime": False,
        "dt": 0.05,
        "window_sec": 1.0,
        "method": "linear",
        "p_lag": 2,
        "n_boot": 8,
        "mi_lag": 1,
        "mi_k": 5,
        "Mmin_db": 3.0,
        "baseline_sec": 3.0,
        "diag_cadence_windows": 100,
        "plant": {"adapter": "sim", "params": {"c_TE": 0.0, "c_RT": 0.0, "c_RE": 0.0}},
        "seed": 11,
    }
    cfg_path = tmp_path / "cfg.yml"
    cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    adv_replay_controller(argparse.Namespace(config=str(cfg_path)))

    runs = os.listdir(tmp_path / "artifacts" / "runs")
    assert len(runs) == 1 and runs[0].startswith("adv-replay-controller")
    audit_path = tmp_path / "artifacts" / "runs" / runs[0] / "audits" / "audit.jsonl"
    events = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    by_name: Dict[str, List[Dict[str, Any]]] = {}
    for e in events:
        by_name.setdefault(e.get("event"), []).append(e)
    header = by_name["run_header"][0]["details"]
    assert header["omega"] == "adv_replay_controller"
    assert by_name.get("adv_replay_tape_recorded")
    assert by_name.get("window_measured")
