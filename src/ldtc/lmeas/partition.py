"""Lmeas: Partition management and greedy regrowth.

Deterministic C/Ex partition representation with hysteresis and a greedy
suggestor to increase loop influence under sparsity penalties.

See Also:
    paper/main.tex — Criterion; Methods: Partitioning algorithm.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple, Dict, Any, Callable


@dataclass
class Partition:
    """C/Ex partition state with freeze flag and flip counter.

    Attributes:
        C: Indices belonging to the loop (closed) set.
        Ex: Indices belonging to the exchange set.
        frozen: If True, updates are suppressed (e.g., during Ω windows).
        flips: Number of accepted partition flips since creation.
    """

    C: List[int]
    Ex: List[int]
    frozen: bool = False
    flips: int = 0


class PartitionManager:
    """Deterministic C/Ex partition with simple hysteresis.

    Provides a minimal manager that can be frozen and updated only when a
    suggested partition yields a sufficient decibel gain ``ΔM`` for a required
    number of consecutive windows.

    Args:
        N_signals: Total number of signals ``N``.
        seed_C: Initial indices for the ``C`` set; remainder form ``Ex``.
    """

    def __init__(self, N_signals: int, seed_C: Sequence[int]) -> None:
        self._N = int(N_signals)
        all_idxs = list(range(self._N))
        C = list(sorted(set(seed_C)))
        Ex = [i for i in all_idxs if i not in C]
        self.part = Partition(C=C, Ex=Ex, frozen=False, flips=0)
        # Hysteresis state
        self._pending_C: Optional[List[int]] = None
        self._pending_streak: int = 0
        self._last_M_db: Optional[float] = None
        # Provenance of the last accepted flip (for audit provenance)
        # Keys: {"streak": int, "delta_M_db": float, "new_C": List[int]}
        self.last_flip_info: Optional[dict] = None

    def get(self) -> Partition:
        """Return the current partition state.

        Returns:
            The :class:`Partition` dataclass instance.
        """
        return self.part

    def freeze(self, on: bool) -> None:
        """Enable or disable freeze to suppress updates.

        Args:
            on: True to freeze, False to unfreeze.
        """
        self.part.frozen = on

    def update_current_M(self, M_db: float) -> None:
        """Record the latest measured M for the current partition.

        Args:
            M_db: Decibel loop-dominance value.
        """
        self._last_M_db = float(M_db)

    def maybe_regrow(
        self,
        suggested_C: Sequence[int],
        delta_M_db: float,
        delta_M_min_db: float = 0.5,
        consecutive_required: int = 3,
    ) -> None:
        """Consider adopting ``suggested_C`` using hysteresis on the ΔM gain.

        Updates are ignored when frozen. Accept only if the same suggestion
        persists for ``consecutive_required`` calls and the gain exceeds
        ``delta_M_min_db``.

        Args:
            suggested_C: Candidate list of indices for C.
            delta_M_db: Decibel gain relative to baseline.
            delta_M_min_db: Minimum required ΔM to count toward acceptance.
            consecutive_required: Number of consecutive ready windows required.
        """
        if self.part.frozen:
            return
        newC = list(sorted(set(suggested_C)))
        if newC == self.part.C:
            # No change requested; reset pending streak
            self._pending_C = None
            self._pending_streak = 0
            return
        # Evaluate hysteresis: require sufficient ΔM and persistence
        if delta_M_db >= delta_M_min_db and (
            self._pending_C == newC or self._pending_C is None
        ):
            self._pending_C = newC
            self._pending_streak += 1
        else:
            # Either insufficient gain or a different suggestion arrived; reset
            self._pending_C = newC
            self._pending_streak = 1 if delta_M_db >= delta_M_min_db else 0
        if self._pending_streak >= consecutive_required:
            # Record provenance before state reset
            self.last_flip_info = {
                "streak": int(self._pending_streak),
                "delta_M_db": float(delta_M_db),
                "new_C": list(newC),
            }
            self.part.C = newC
            all_idxs = list(range(self._N))
            self.part.Ex = [i for i in all_idxs if i not in newC]
            self.part.flips += 1
            # reset pending
            self._pending_C = None
            self._pending_streak = 0


def greedy_suggest_C(
    X: Any,
    C: List[int] | Sequence[int],
    Ex: List[int] | Sequence[int],
    *,
    estimator: Callable[..., Any],
    method: str = "linear",
    p: int = 3,
    lag_mi: int = 1,
    n_boot_candidates: int = 8,
    mi_k: int = 5,
    lam: float = 0.0,
    theta: float = 0.0,
    kappa: int | None = None,
) -> Tuple[List[int], float, Dict[str, Any]]:
    """Greedy regrowth of C using ΔL_loop gain with sparsity penalty.

    Starting from the current C/Ex, iteratively add the candidate from Ex that
    maximizes the penalized gain in ``L_loop`` until the marginal gain falls
    below ``theta`` or a cap ``kappa`` is reached.

    Args:
        X: Telemetry matrix (T, N) consumed by ``estimator``.
        C: Current loop set indices.
        Ex: Current exchange set indices.
        estimator: Callable compatible with :func:`ldtc.lmeas.estimators.estimate_L`.
        method: Estimation method forwarded to ``estimator``.
        p: VAR order for linear estimator.
        lag_mi: Lag for MI-based estimators.
        n_boot_candidates: Number of bootstrap draws used during candidate eval.
        mi_k: k-NN parameter for Kraskov MI.
        lam: Sparsity penalty per added node.
        theta: Minimum penalized gain to accept a candidate.
        kappa: Optional cap on |C|.

    Returns:
        Tuple ``(suggested_C, delta_M_db, details)`` where ``details`` contains
        provenance about added indices and intermediate gains.
    """
    from .metrics import m_db as _m_db

    C_cur: List[int] = list(sorted(set(int(i) for i in C)))
    Ex_cur: List[int] = [i for i in range(int(X.shape[1])) if i not in C_cur]
    # Baseline
    base = estimator(
        X=X,
        C=C_cur,
        Ex=Ex_cur,
        method=method,
        p=p,
        lag_mi=lag_mi,
        n_boot=max(0, int(n_boot_candidates)),
        mi_k=mi_k,
    )
    L_loop_base = float(base.L_loop)
    M_base = _m_db(base.L_loop, base.L_ex)

    def _penalty(_n: int) -> float:
        # Simple ℓ0-style penalty per add; configurable hooks can extend this later
        return 1.0

    added: List[int] = []
    step_gains: List[float] = []
    while True:
        if kappa is not None and len(C_cur) >= int(kappa):
            break
        best_score = float("-inf")
        best_idx: Optional[int] = None
        best_L_loop_new: Optional[float] = None
        # Evaluate candidates in lexicographic order for deterministic tie-breaking
        for ex_idx in sorted(Ex_cur):
            cand_C = sorted(C_cur + [ex_idx])
            cand_Ex = [i for i in range(int(X.shape[1])) if i not in cand_C]
            res = estimator(
                X=X,
                C=cand_C,
                Ex=cand_Ex,
                method=method,
                p=p,
                lag_mi=lag_mi,
                n_boot=max(0, int(n_boot_candidates)),
                mi_k=mi_k,
            )
            L_loop_new = float(res.L_loop)
            score = (L_loop_new - L_loop_base) - float(lam) * _penalty(ex_idx)
            if score > best_score:
                best_score = score
                best_idx = ex_idx
                best_L_loop_new = L_loop_new
        if best_idx is None or best_score < float(theta):
            break
        # Commit best candidate to temporary suggestion and continue
        C_cur.append(int(best_idx))
        C_cur = sorted(set(C_cur))
        Ex_cur = [i for i in range(int(X.shape[1])) if i not in C_cur]
        L_loop_base = (
            float(best_L_loop_new) if best_L_loop_new is not None else L_loop_base
        )
        added.append(int(best_idx))
        step_gains.append(float(best_score))

    # Compute final ΔM relative to original baseline for hysteresis decision
    final = estimator(
        X=X,
        C=C_cur,
        Ex=Ex_cur,
        method=method,
        p=p,
        lag_mi=lag_mi,
        n_boot=max(0, int(n_boot_candidates)),
        mi_k=mi_k,
    )
    M_final = _m_db(final.L_loop, final.L_ex)
    delta_M_db = float(M_final - M_base)
    details: Dict[str, Any] = {
        "added": list(added),
        "num_steps": len(added),
        "step_gains": list(step_gains),
        "M_base": float(M_base),
        "M_final": float(M_final),
    }
    return list(C_cur), delta_M_db, details
