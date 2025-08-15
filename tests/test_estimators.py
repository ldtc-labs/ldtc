from __future__ import annotations
import numpy as np

from ldtc.lmeas.estimators import estimate_L
from ldtc.lmeas.metrics import sc1_evaluate


def test_sc1_evaluate_basic():
    ok, stats = sc1_evaluate(
        L_loop_baseline=1.0,
        L_loop_trough=0.9,
        L_loop_recovered=1.0,
        M_post=3.2,
        epsilon=0.15,
        tau_rec_measured=5.0,
        Mmin=3.0,
        tau_max=10.0,
    )
    assert ok is True
    assert abs(stats.delta - 0.1) < 1e-6


def test_sc1_evaluate_edge_failures():
    # Too large delta
    ok1, stats1 = sc1_evaluate(
        L_loop_baseline=1.0,
        L_loop_trough=0.7,  # 30% drop
        L_loop_recovered=1.0,
        M_post=3.2,
        epsilon=0.15,
        tau_rec_measured=5.0,
        Mmin=3.0,
        tau_max=10.0,
    )
    assert ok1 is False and stats1.delta > 0.15
    # tau_rec too large
    ok2, _ = sc1_evaluate(
        L_loop_baseline=1.0,
        L_loop_trough=0.9,
        L_loop_recovered=1.0,
        M_post=3.2,
        epsilon=0.15,
        tau_rec_measured=12.0,  # exceeds tau_max
        Mmin=3.0,
        tau_max=10.0,
    )
    assert ok2 is False
    # M_post below Mmin
    ok3, _ = sc1_evaluate(
        L_loop_baseline=1.0,
        L_loop_trough=0.9,
        L_loop_recovered=1.0,
        M_post=2.9,
        epsilon=0.15,
        tau_rec_measured=5.0,
        Mmin=3.0,
        tau_max=10.0,
    )
    assert ok3 is False


def test_estimate_L_shapes():
    # White noise with slight causal link 1->0
    rng = np.random.default_rng(0)
    T = 400
    x1 = rng.normal(size=T)
    x0 = np.zeros(T)
    for t in range(1, T):
        x0[t] = 0.5 * x1[t - 1] + 0.5 * x0[t - 1] + rng.normal(scale=0.1)
    X = np.column_stack([x0, x1])
    res = estimate_L(X, C=[0], Ex=[1], method="linear", p=2, n_boot=8)
    assert res.L_loop >= 0.0
    assert res.L_ex >= 0.0
