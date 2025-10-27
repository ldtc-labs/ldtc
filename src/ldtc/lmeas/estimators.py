"""Lmeas: Estimators for loop and exchange influence (L).

Lightweight predictive-dependence estimators used to compute loop influence
``L_loop`` and exchange influence ``L_ex`` over a C/Ex partition. Includes
linear (Granger-like) and mutual information methods, with optional TE/DI
proxies. Confidence intervals are computed via circular block bootstrap per
window.

See Also:
    paper/main.tex — Criterion; Methods: Measurement & Attestation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence, Tuple, Callable

import numpy as np
from sklearn.feature_selection import mutual_info_regression
from scipy.spatial import cKDTree
from scipy.special import digamma
import importlib
import importlib.util
from ldtc.runtime.windows import block_bootstrap_indices
from .diagnostics import var_nt_ratio

# Lightweight lagged linear-Granger-like estimator
# and mutual information aggregators (sklearn and Kraskov k-NN).
#
# We treat 'signals' as a matrix X (T, N), with `order` naming columns.
# Given partition sets C (indices) and Ex (indices), we compute:
#   L_loop: average directed influence among nodes in C (excluding self)
#   L_exchange: average directed influence from Ex -> nodes in C
# Returns point estimates and simple bootstrap CIs.


@dataclass
class LResult:
    """Result container for loop/exchange influence and CI bounds.

    Attributes:
        L_loop: Point estimate of loop influence.
        L_ex: Point estimate of exchange influence.
        ci_loop: Tuple of (lo, hi) CI bounds for ``L_loop``.
        ci_ex: Tuple of (lo, hi) CI bounds for ``L_ex``.
    """

    L_loop: float
    L_ex: float
    ci_loop: Tuple[float, float]
    ci_ex: Tuple[float, float]


def _lag_matrix(x: np.ndarray, p: int) -> Tuple[np.ndarray, np.ndarray]:
    """Construct lagged design matrix and targets for VAR-like regression.

    Args:
        x: Array of shape (T, N), time major.
        p: Number of lags to include (p >= 1).

    Returns:
        A tuple ``(X, Y)`` where ``X`` has shape (T - p, N*p) and ``Y`` has
        shape (T - p, N) containing the aligned, non-overlapping targets.

    Raises:
        ValueError: If there are not enough samples (T <= p).
    """
    T, N = x.shape
    if T <= p:
        raise ValueError("Not enough samples for lagged model")
    Y = x[p:]
    Xlags = []
    for lag in range(1, p + 1):
        Xlags.append(x[p - lag : T - lag])
    X = np.concatenate(Xlags, axis=1)  # (T-p, N*p)
    return X, Y


def _dir_influence_linear_conditional(
    x: np.ndarray,
    p: int,
    add_sources: Sequence[int],
    base_sources: Sequence[int],
    targets: Sequence[int],
) -> float:
    """Partial R^2 improvement from additional lagged sources to targets.

    Computes the average improvement in explained variance for target signals
    when adding lagged predictors from ``add_sources`` on top of an AR baseline
    and lagged ``base_sources``.

    Args:
        x: Array of shape (T, N) with time along the first dimension.
        p: Number of lags for the linear model.
        add_sources: Indices of candidate source signals to add.
        base_sources: Indices included in the baseline model (besides AR of target).
        targets: Target signal indices to evaluate.

    Returns:
        Mean partial R^2 improvement across ``targets``.
    """
    X, Y = _lag_matrix(x, p)
    Tm, N = Y.shape
    Nsig = N

    def cols_for(indices: Sequence[int]) -> List[int]:
        out: List[int] = []
        idx_arr = np.array(indices, dtype=int)
        for lag in range(p):
            out.extend((idx_arr + lag * Nsig).tolist())
        return out

    r2_improvements = []
    for t in targets:
        cols_ar = np.array(cols_for([t]), dtype=int)
        # Exclude the target from add/base sources to avoid self-lag duplication
        base_eff = [s for s in base_sources if s != t]
        add_eff = [s for s in add_sources if s != t]
        cols_base = (
            np.array(cols_for(base_eff), dtype=int)
            if len(base_eff)
            else np.array([], dtype=int)
        )
        cols_add = (
            np.array(cols_for(add_eff), dtype=int)
            if len(add_eff)
            else np.array([], dtype=int)
        )
        # Build baseline and additional predictor matrices
        X_base = (
            np.concatenate([X[:, cols_ar], X[:, cols_base]], axis=1)
            if len(cols_base)
            else X[:, cols_ar]
        )
        A_add = X[:, cols_add] if len(cols_add) else np.zeros((X.shape[0], 0))
        y = Y[:, t]
        # Compute partial R^2 of add predictors given baseline using QR residualization
        if X_base.size == 0:
            # Should not occur; fallback to variance about mean
            r = y - np.mean(y)
            A_perp = A_add
        else:
            Qb, _ = np.linalg.qr(X_base, mode="reduced")
            yhat_b = Qb @ (Qb.T @ y)
            r = y - yhat_b
            if A_add.size:
                A_perp = A_add - Qb @ (Qb.T @ A_add)
            else:
                A_perp = A_add
        denom = float(np.sum(r * r)) + 1e-12
        if A_perp.size == 0:
            r2_add = 0.0
        else:
            beta_add, *_ = np.linalg.lstsq(A_perp, r, rcond=None)
            rhat = A_perp @ beta_add
            num = float(np.sum(rhat * rhat))
            r2_add = max(0.0, min(1.0, num / denom))
        r2_improvements.append(r2_add)
    return float(np.mean(r2_improvements)) if r2_improvements else 0.0


def _dir_influence_linear(
    x: np.ndarray, p: int, sources: Sequence[int], targets: Sequence[int]
) -> float:
    """Convenience wrapper for linear influence without baseline sources.

    Equivalent to calling :func:`_dir_influence_linear_conditional` with an empty
    ``base_sources`` list.
    """
    # Backward-compatible wrapper: add_sources vs AR-only baseline
    return _dir_influence_linear_conditional(
        x=x, p=p, add_sources=sources, base_sources=[], targets=targets
    )


def _dir_influence_mi(
    x: np.ndarray, sources: Sequence[int], targets: Sequence[int], lag: int = 1
) -> float:
    """Average pairwise mutual information from sources to targets.

    Computes MI between ``sources`` at time ``t-lag`` and ``targets`` at time
    ``t`` using sklearn's kNN-based estimator.

    Args:
        x: Array of shape (T, N), time major.
        sources: Indices of source signals.
        targets: Indices of target signals.
        lag: Positive lag between sources and targets (default 1 sample).

    Returns:
        Mean mutual information across all source-target pairs.
    """
    T, N = x.shape
    if T <= lag:
        return 0.0
    vals: List[float] = []
    for t in targets:
        y = x[lag:, t]
        for s in sources:
            if s == t:
                continue
            xs = x[:-lag, s]
            # sklearn MI expects 2D X
            mi = mutual_info_regression(xs.reshape(-1, 1), y, discrete_features=False)
            vals.append(float(mi[0]))
    return float(np.mean(vals)) if vals else 0.0


def _mi_ksg(x: np.ndarray, y: np.ndarray, k: int = 5) -> float:
    """Kraskov–Stögbauer–Grassberger (KSG-I) mutual information.

    Estimates MI between two continuous variables using k-nearest neighbors with
    Chebyshev metric.

    Args:
        x: Array-like, will be coerced to shape (T, 1).
        y: Array-like, will be coerced to shape (T, 1).
        k: Neighborhood size for KSG (default 5).

    Returns:
        Estimated mutual information in nats.
    """
    x = np.asarray(x, dtype=float).reshape(-1, 1)
    y = np.asarray(y, dtype=float).reshape(-1, 1)
    if x.shape[0] != y.shape[0]:
        raise ValueError("x and y must have the same number of samples")
    n = int(x.shape[0])
    if n <= k:
        return 0.0
    # Joint tree with Chebyshev metric (max-norm)
    joint = np.hstack([x, y])
    tree_joint = cKDTree(joint, leafsize=32)
    # Distances to k-th neighbor (exclude the point itself by k+1 in query)
    # Use a tiny epsilon to ensure strictly inside counts on marginals
    eps = 1e-10
    dists, _ = tree_joint.query(joint, k=k + 1, p=np.inf)
    rk = np.maximum(dists[:, -1] - eps, 0.0)
    # Marginal counts within Chebyshev radius rk
    tree_x = cKDTree(x, leafsize=32)
    tree_y = cKDTree(y, leafsize=32)
    nx = np.fromiter(
        (len(tree_x.query_ball_point(x[i], rk[i], p=np.inf)) - 1 for i in range(n)),
        dtype=int,
    )
    ny = np.fromiter(
        (len(tree_y.query_ball_point(y[i], rk[i], p=np.inf)) - 1 for i in range(n)),
        dtype=int,
    )
    # Guard against degenerate neighborhoods (clip to >=0)
    nx = np.clip(nx, 0, None)
    ny = np.clip(ny, 0, None)
    # KSG I estimator
    val = digamma(k) + digamma(n) - np.mean(digamma(nx + 1) + digamma(ny + 1))
    return float(max(0.0, val))


def _dir_influence_mi_kraskov(
    x: np.ndarray,
    sources: Sequence[int],
    targets: Sequence[int],
    lag: int = 1,
    k: int = 5,
) -> float:
    """Average pairwise KSG MI from sources to targets.

    Args:
        x: Array of shape (T, N), time major.
        sources: Indices of source signals.
        targets: Indices of target signals.
        lag: Positive lag between sources and targets (default 1 sample).
        k: k-NN parameter for the KSG estimator.

    Returns:
        Mean KSG MI across all source-target pairs.
    """
    T, N = x.shape
    if T <= lag:
        return 0.0
    vals: List[float] = []
    for t in targets:
        y = x[lag:, t]
        for s in sources:
            if s == t:
                continue
            xs = x[:-lag, s]
            vals.append(_mi_ksg(xs, y, k=k))
    return float(np.mean(vals)) if vals else 0.0


def _maybe_te_backend() -> (
    Callable[[np.ndarray, Sequence[int], Sequence[int], int], float] | None
):
    """Optionally provide a transfer-entropy-like backend.

    Tries to import a light-weight proxy using ``tigramite``. If available,
    returns a callable ``te(arr, sources, targets, lag)``; otherwise ``None``.
    """
    # Placeholder: detect tigramite and use its ParCorr-based CMI TE if present.
    try:
        if importlib.util.find_spec("tigramite") is None:
            return None
        # Defer heavy imports until used
        from tigramite.independence_tests import ParCorr
        from tigramite import data_processing as pp
        from tigramite import pcmci as pcmci_mod

        def te_fn(
            arr: np.ndarray, sources: Sequence[int], targets: Sequence[int], lag: int
        ) -> float:
            # Compute average TE from sources->targets at given lag using PCMCI+ParCorr proxy.
            # Note: This is a linearized TE proxy. For full TE, users should configure IDTxl.
            if arr.ndim != 2:
                return 0.0
            dataframe = pp.DataFrame(arr, datatime=None)
            pcmci = pcmci_mod.PCMCI(dataframe=dataframe, cond_ind_test=ParCorr())
            # Run partial correlation at lag; approximate TE by partial correlation magnitude
            vals: List[float] = []
            for t in targets:
                for s in sources:
                    if s == t:
                        continue
                    # Run partial correlation test X_{t-lag} -> Y_t | Y_{t-1}
                    res = pcmci.get_lagged_dependencies(
                        selected_variables=[t],
                        tau_max=lag,
                        val_only=True,
                    )
                    # Extract score if present
                    try:
                        score = abs(float(res["val_matrix"][t, s, lag]))
                    except Exception:
                        score = 0.0
                    vals.append(score)
            return float(np.mean(vals)) if vals else 0.0

        return te_fn
    except Exception:
        return None


def _maybe_di_backend() -> (
    Callable[[np.ndarray, Sequence[int], Sequence[int], int], float] | None
):
    """Optionally provide a directed-information backend.

    Currently returns ``None`` to trigger MI-based proxy.
    """
    # No lightweight DI backend by default; return None to trigger fallback.
    return None


def _bootstrap(
    x: np.ndarray,
    fn: Callable[[np.ndarray], float],
    n_draws: int = 64,
    block: int | None = None,
) -> Tuple[float, float]:
    """Bootstrap confidence interval (percentile, ~95%).

    Performs circular block bootstrap resampling of the time axis.

    Args:
        x: Array of shape (T, N) or (T, ...). Only the first dimension (time)
            is resampled; the array is passed to ``fn`` after indexing.
        fn: Estimator function mapping an array like ``x[idx]`` to a scalar.
        n_draws: Number of bootstrap replicates.
        block: Block length; defaults to ``max(4, T//4)``.

    Returns:
        Tuple of (lo, hi) percentile CI bounds.
    """
    T = x.shape[0]
    if T < 12:
        return (np.nan, np.nan)
    # Default block length ~ window/4, with a small floor
    blk = int(block) if block is not None else max(4, T // 4)
    idxs = block_bootstrap_indices(T, blk, n_draws)
    vals: List[float] = []
    for idx in idxs:
        vals.append(fn(x[idx]))
    arr = np.asarray(vals, dtype=float)
    lo, hi = np.nanpercentile(arr, [2.5, 97.5]).tolist()
    return lo, hi


def estimate_L(
    X: np.ndarray,
    C: Sequence[int],
    Ex: Sequence[int],
    method: str = "linear",
    p: int = 3,
    lag_mi: int = 1,
    n_boot: int = 64,
    mi_k: int = 5,
) -> LResult:
    """Estimate loop and exchange influence.

    Computes ``L_loop`` over partition ``C`` and ``L_ex`` from ``Ex -> C`` using
    the selected predictive dependence metric.

    Args:
        X: Time-by-signal matrix of shape (T, N).
        C: Indices of the loop partition.
        Ex: Indices of the exchange partition.
        method: One of ``{"linear", "mi", "mi_kraskov", "transfer_entropy", "directed_information"}``.
        p: VAR order for linear estimator.
        lag_mi: Lag between sources and targets for MI/TE/DI methods.
        n_boot: Number of bootstrap draws for CI estimation.
        mi_k: k-NN parameter for Kraskov MI.

    Returns:
        ``LResult`` with point estimates and (lo, hi) CI bounds for each metric.

    Raises:
        ValueError: If ``method`` is not supported.
    """
    if method not in (
        "linear",
        "mi",
        "mi_kraskov",
        "transfer_entropy",
        "directed_information",
    ):
        raise ValueError(
            "method must be 'linear', 'mi', 'mi_kraskov', 'transfer_entropy', or 'directed_information'"
        )
    C = list(C)
    Ex = list(Ex)
    # N = X.shape[1]
    # Targets are nodes in C
    if method == "linear":

        def Lloop_fn(arr: np.ndarray) -> float:
            # Condition on Ex when assessing loop influence
            return _dir_influence_linear_conditional(
                arr, p=p, add_sources=C, base_sources=Ex, targets=C
            )

        def Lex_fn(arr: np.ndarray) -> float:
            # Condition on C when assessing exchange influence
            return _dir_influence_linear_conditional(
                arr, p=p, add_sources=Ex, base_sources=C, targets=C
            )

    elif method == "mi":

        def Lloop_fn(arr: np.ndarray) -> float:
            return _dir_influence_mi(arr, sources=C, targets=C, lag=lag_mi)

        def Lex_fn(arr: np.ndarray) -> float:
            return _dir_influence_mi(arr, sources=Ex, targets=C, lag=lag_mi)

    elif method == "mi_kraskov":

        def Lloop_fn(arr: np.ndarray) -> float:
            return _dir_influence_mi_kraskov(
                arr, sources=C, targets=C, lag=lag_mi, k=mi_k
            )

        def Lex_fn(arr: np.ndarray) -> float:
            return _dir_influence_mi_kraskov(
                arr, sources=Ex, targets=C, lag=lag_mi, k=mi_k
            )

    else:
        # Optional TE/DI plugin backends with graceful fallback to MI proxy
        te_backend = _maybe_te_backend() if method == "transfer_entropy" else None
        di_backend = _maybe_di_backend() if method == "directed_information" else None

        def _proxy(arr: np.ndarray, src: Sequence[int], tgt: Sequence[int]) -> float:
            return _dir_influence_mi_kraskov(
                arr, sources=src, targets=tgt, lag=max(1, lag_mi), k=mi_k
            )

        def Lloop_fn(arr: np.ndarray) -> float:
            if method == "transfer_entropy" and te_backend is not None:
                return te_backend(arr, C, C, max(1, lag_mi))
            if method == "directed_information" and di_backend is not None:
                return di_backend(arr, C, C, max(1, lag_mi))
            return _proxy(arr, C, C)

        def Lex_fn(arr: np.ndarray) -> float:
            if method == "transfer_entropy" and te_backend is not None:
                return te_backend(arr, Ex, C, max(1, lag_mi))
            if method == "directed_information" and di_backend is not None:
                return di_backend(arr, Ex, C, max(1, lag_mi))
            return _proxy(arr, Ex, C)

    # Warn (via NaN CI sentinel) if VAR N/T is marginal for the chosen p when using linear estimator
    if method == "linear":
        ratio = var_nt_ratio(X.shape[0], X.shape[1], p)
        # If highly marginal (< ~1.5 samples per parameter), return wide CIs by design
        marginal = ratio < 1.5
    else:
        marginal = False

    L_loop = float(Lloop_fn(X))
    L_ex = float(Lex_fn(X))
    ci_loop = _bootstrap(X, Lloop_fn, n_draws=n_boot)
    ci_ex = _bootstrap(X, Lex_fn, n_draws=n_boot)
    if marginal:
        # Inflate CIs to signal uncertainty and allow smell-tests to invalidate
        try:
            wL = abs(ci_loop[1] - ci_loop[0])
            wE = abs(ci_ex[1] - ci_ex[0])
            ci_loop = (ci_loop[0] - wL, ci_loop[1] + wL)
            ci_ex = (ci_ex[0] - wE, ci_ex[1] + wE)
        except Exception:
            pass
    return LResult(L_loop=L_loop, L_ex=L_ex, ci_loop=ci_loop, ci_ex=ci_ex)
