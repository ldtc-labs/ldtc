"""Diagnostic helpers for measurement stability.

Wrappers for ADF / KPSS stationarity tests, a stationarity summary
dataclass, and a VAR N/T ratio heuristic. These are used to annotate audit
records and to guard the loop-influence estimators against ill-posed
regimes (too few samples per parameter, non-stationary series, and so on).

See Also:
    `paper/main.tex`: Methods: Measurement; Smell-tests and invalidation.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np
from statsmodels.tools.sm_exceptions import InterpolationWarning
from statsmodels.tsa.stattools import adfuller, kpss


@dataclass
class StationaritySummary:
    """Summary of per-series stationarity flags.

    Attributes:
        adf_nonstationary_frac: Fraction flagged non-stationary by ADF (fails
            to reject the unit-root null at 5%).
        kpss_nonstationary_frac: Fraction flagged non-stationary by KPSS
            (rejects stationarity at 5%).
        per_series: List of tuples `(adf_nonstat, kpss_nonstat)` per column.
    """

    adf_nonstationary_frac: float
    kpss_nonstationary_frac: float
    per_series: List[Tuple[bool, bool]]  # (adf_nonstat, kpss_nonstat) per column


def _safe_adf(x: np.ndarray) -> bool:
    """ADF non-stationarity flag with error handling.

    Returns True if the series appears non-stationary at 5% (fail to reject
    unit root), and True on errors as a conservative default.
    """
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            res = adfuller(x, autolag="AIC")
        p = float(res[1])
        return p >= 0.05
    except Exception:
        # Be conservative: if test fails, mark as non-stationary
        return True


def _safe_kpss(x: np.ndarray) -> bool:
    """KPSS non-stationarity flag with error handling.

    Returns True if the series appears non-stationary at 5% (reject
    stationarity). On failures (common on short series), returns False to avoid
    double penalization with ADF.
    """
    try:
        # Suppress noisy interpolation warnings about p-value table bounds
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", InterpolationWarning)
            warnings.simplefilter("ignore", RuntimeWarning)
            stat, p, *_ = kpss(x, regression="c", nlags="auto")
        return p < 0.05
    except Exception:
        # If KPSS fails (common on short series), do not double-penalize: assume stationary
        return False


def stationarity_checks(X: np.ndarray) -> StationaritySummary:
    """Run ADF and KPSS per column and summarize.

    Args:
        X: Array of shape `(T, N)` with time along axis 0.

    Returns:
        A [`StationaritySummary`][ldtc.lmeas.diagnostics.StationaritySummary]
        with per-series flags and overall fractions.

    Raises:
        ValueError: If `X` is not a 2D array.
    """
    if X.ndim != 2:
        raise ValueError("X must be (T, N)")
    T, N = X.shape
    per_series: List[Tuple[bool, bool]] = []
    for j in range(N):
        xj = np.asarray(X[:, j], dtype=float)
        adf_ns = _safe_adf(xj)
        kpss_ns = _safe_kpss(xj)
        per_series.append((adf_ns, kpss_ns))
    adf_nonstat = sum(1 for a, _ in per_series if a)
    kpss_nonstat = sum(1 for _, k in per_series if k)
    return StationaritySummary(
        adf_nonstationary_frac=(adf_nonstat / max(1, N)),
        kpss_nonstationary_frac=(kpss_nonstat / max(1, N)),
        per_series=per_series,
    )


def var_nt_ratio(T: int, N: int, p: int) -> float:
    """Rule-of-thumb samples-per-parameter ratio for VAR(p).

    Computes `(T - p) / (N * p)` where `T` is the number of time samples,
    `N` is the number of signals, and `p` is the VAR lag order. Lower
    values indicate a more marginal regression setting; the linear
    estimator in
    [`estimate_L`][ldtc.lmeas.estimators.estimate_L] inflates its CIs when
    this ratio drops below ~1.5.

    Args:
        T: Number of time samples.
        N: Number of signals (columns).
        p: VAR lag order.

    Returns:
        Samples-per-parameter ratio. Returns `inf` if `N` or `p` is
        non-positive (ill-defined regression).
    """
    if N <= 0 or p <= 0:
        return float("inf")
    return max(0.0, float(T - p)) / float(N * p)
