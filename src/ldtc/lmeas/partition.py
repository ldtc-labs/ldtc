from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple, Dict, Any, Callable


@dataclass
class Partition:
    C: List[int]
    Ex: List[int]
    frozen: bool = False
    flips: int = 0


class PartitionManager:
    """
    Deterministic C/Ex partition with simple hysteresis:
    - Start from seeded C.
    - Periodically 're-grows' by moving nodes that increase L_loop more than a threshold.
      (For this reference implementation we keep a simple fixed assignment with an optional flip hook.)
    - Can be 'frozen' during Ω.
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
        return self.part

    def freeze(self, on: bool) -> None:
        self.part.frozen = on

    def update_current_M(self, M_db: float) -> None:
        """Record the latest measured M for the current (C, Ex)."""
        self._last_M_db = float(M_db)

    def maybe_regrow(
        self,
        suggested_C: Sequence[int],
        delta_M_db: float,
        delta_M_min_db: float = 0.5,
        consecutive_required: int = 3,
    ) -> None:
        """
        Consider adopting `suggested_C` using hysteresis on the loop-dominance gain.

        - Changes are ignored when frozen.
        - Accept only if the same suggestion persists and its ΔM ≥ delta_M_min_db
          for `consecutive_required` consecutive ready windows.
        - On accept, recompute Ex deterministically and count a flip.
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
    """
    Deterministic greedy regrowth of C using ΔL_loop gain with sparsity penalty.

    - Start from current C, Ex.
    - At each step, evaluate all n in Ex: Δ = L_loop(C∪{n}) − L_loop(C) − lam·pen(n).
      Use lexicographic tie-break (sorted Ex) and add argmax if Δ ≥ theta.
    - Stop if no candidate meets theta or |C| reaches kappa (if provided).
    - Return (suggested_C, delta_M_db, details).

    Hysteresis over ΔM (dB) is applied by the caller via PartitionManager.maybe_regrow.
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
