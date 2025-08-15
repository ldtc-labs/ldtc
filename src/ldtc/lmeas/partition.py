from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence


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
      (For hello-world we keep a simple fixed assignment with an optional flip hook.)
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
