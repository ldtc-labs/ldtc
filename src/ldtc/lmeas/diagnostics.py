from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

import numpy as np
import warnings
from statsmodels.tsa.stattools import adfuller, kpss
from statsmodels.tools.sm_exceptions import InterpolationWarning


@dataclass
class StationaritySummary:
    adf_nonstationary_frac: float
    kpss_nonstationary_frac: float
    per_series: List[Tuple[bool, bool]]  # (adf_nonstat, kpss_nonstat) per column


def _safe_adf(x: np.ndarray) -> bool:
    """
    Returns True if series appears non-stationary under ADF at 5% (fail to reject unit root).
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
    """
    Returns True if series appears non-stationary under KPSS at 5% (reject stationarity).
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
    """
    Run ADF and KPSS per column of X (T, N). Return per-series flags and fractions.
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
    """
    Rule-of-thumb samples-per-parameter ratio for a VAR(p) with N signals.
    Returns (T - p) / (N * p). Lower values are more marginal.
    """
    if N <= 0 or p <= 0:
        return float("inf")
    return max(0.0, float(T - p)) / float(N * p)
