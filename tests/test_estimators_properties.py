from __future__ import annotations

import numpy as np

from ldtc.lmeas.estimators import estimate_L
from ldtc.lmeas.metrics import m_db


def _gen_var2_with_exchange(
    T: int, c_intra: float, k_ex: float, seed: int = 0
) -> np.ndarray:
    """
    Generate a simple 3-node linear dynamical system:
      - Nodes 0 and 1 are in the loop (C); symmetric coupling c_intra between them + AR(1) self term.
      - Node 2 is exchange (Ex); AR(1) and drives both 0 and 1 with fixed coupling k_ex.
    Returns X with shape (T, 3).
    """
    rng = np.random.default_rng(seed)
    a_self = 0.4
    a_ex = 0.6
    x0 = np.zeros(T)
    x1 = np.zeros(T)
    x2 = np.zeros(T)
    for t in range(1, T):
        x2[t] = a_ex * x2[t - 1] + rng.normal(0.0, 0.5)
        eps0 = rng.normal(0.0, 0.5)
        eps1 = rng.normal(0.0, 0.5)
        x0[t] = a_self * x0[t - 1] + c_intra * x1[t - 1] + k_ex * x2[t - 1] + eps0
        x1[t] = a_self * x1[t - 1] + c_intra * x0[t - 1] + k_ex * x2[t - 1] + eps1
    return np.column_stack([x0, x1, x2])


def _compute_M_db(X: np.ndarray, method: str) -> float:
    kwargs = {"p": 2, "n_boot": 32}
    if method.startswith("mi"):
        kwargs.update({"lag_mi": 1})
        if method == "mi_kraskov":
            kwargs.update({"mi_k": 5})
    res = estimate_L(X, C=[0, 1], Ex=[2], method=method, **kwargs)
    return m_db(res.L_loop, res.L_ex)


def test_monotonicity_increasing_intra_coupling_raises_M_db():
    # Increasing intra-loop coupling should raise loop dominance M (dB)
    ks = [0.0, 0.2, 0.4, 0.6]
    Ms = []
    for k in ks:
        X = _gen_var2_with_exchange(T=1600, c_intra=k, k_ex=0.2, seed=123)
        Ms.append(_compute_M_db(X, method="linear"))
    # Assert monotonic non-decreasing with a small slack
    for a, b in zip(Ms, Ms[1:]):
        assert b >= a - 1e-3, f"M not monotonic: {Ms}"


def test_bootstrap_ci_shrinks_with_more_samples():
    # For fixed dynamics, bootstrap CI width should shrink as T increases
    X_small = _gen_var2_with_exchange(T=400, c_intra=0.4, k_ex=0.2, seed=7)
    X_big = _gen_var2_with_exchange(T=2400, c_intra=0.4, k_ex=0.2, seed=7)
    res_small = estimate_L(X_small, C=[0, 1], Ex=[2], method="linear", p=2, n_boot=64)
    res_big = estimate_L(X_big, C=[0, 1], Ex=[2], method="linear", p=2, n_boot=64)
    w_loop_small = res_small.ci_loop[1] - res_small.ci_loop[0]
    w_loop_big = res_big.ci_loop[1] - res_big.ci_loop[0]
    w_ex_small = res_small.ci_ex[1] - res_small.ci_ex[0]
    w_ex_big = res_big.ci_ex[1] - res_big.ci_ex[0]
    # Allow a little stochastic variance but expect shrinkage
    assert w_loop_big <= w_loop_small * 0.85, (w_loop_small, w_loop_big)
    assert w_ex_big <= w_ex_small * 0.85, (w_ex_small, w_ex_big)


def test_mi_and_linear_estimators_agree_on_linear_system():
    # Both estimators should reflect the same ordering as intra-loop coupling increases
    ks = [0.1, 0.4, 0.7]
    Ms_lin = []
    Ms_mi = []
    Ms_ksg = []
    for k in ks:
        X = _gen_var2_with_exchange(T=2000, c_intra=k, k_ex=0.2, seed=99)
        Ms_lin.append(_compute_M_db(X, method="linear"))
        Ms_mi.append(_compute_M_db(X, method="mi"))
        Ms_ksg.append(_compute_M_db(X, method="mi_kraskov"))
    # Monotonic non-decreasing for both
    for a, b in zip(Ms_lin, Ms_lin[1:]):
        assert b >= a - 1e-3, f"Linear M not monotonic: {Ms_lin}"
    for a, b in zip(Ms_mi, Ms_mi[1:]):
        assert b >= a - 1e-3, f"MI M not monotonic: {Ms_mi}"
    for a, b in zip(Ms_ksg, Ms_ksg[1:]):
        assert b >= a - 1e-3, f"KSG MI M not monotonic: {Ms_ksg}"
    # And the direction of change (delta between endpoints) matches
    assert (Ms_lin[-1] - Ms_lin[0]) >= 0.0
    assert (Ms_mi[-1] - Ms_mi[0]) >= 0.0
