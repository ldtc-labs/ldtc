from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass
class LEntry:
    L_loop: float
    L_ex: float
    ci_loop: Tuple[float, float]
    ci_ex: Tuple[float, float]
    M_db: float
    nc1_pass: bool


class LREG:
    """
    Enclave-like store for raw L and CI. Write-only from measurement pipeline.
    Exposes only derived indicators via derive().
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: Dict[int, LEntry] = {}
        self._counter = 0
        self._invalidated = False
        self._reason: Optional[str] = None

    @property
    def invalidated(self) -> bool:
        return self._invalidated

    @property
    def reason(self) -> Optional[str]:
        return self._reason

    def write(self, entry: LEntry) -> int:
        with self._lock:
            idx = self._counter
            self._entries[idx] = entry
            self._counter += 1
            return idx

    def invalidate(self, reason: str) -> None:
        with self._lock:
            self._invalidated = True
            self._reason = reason

    def latest(self) -> Optional[LEntry]:
        with self._lock:
            if not self._entries:
                return None
            return self._entries[max(self._entries.keys())]

    # No raw read API exposed for external callers
    # (Keep the "enclave" boundary intact.)

    def derive(self) -> Dict[str, float | int | bool]:
        """Return only derived indicators."""
        ent = self.latest()
        if not ent:
            return {
                "nc1": False,
                "M_db": 0.0,
                "counter": 0,
                "invalidated": self._invalidated,
            }
        return {
            "nc1": ent.nc1_pass and not self._invalidated,
            "M_db": ent.M_db,
            "counter": len(self._entries),
            "invalidated": self._invalidated,
        }
