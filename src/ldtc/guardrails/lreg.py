"""Guardrails: LREG enclave.

In-memory enclave-like register for raw loop/exchange values and CIs, exposing
only derived indicators externally to honor the no-raw-LREG policy.

See Also:
    paper/main.tex — Methods: Measurement & Attestation; Export policy.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass
class LEntry:
    """Raw LREG entry for a single window.

    Attributes:
        L_loop: Loop influence.
        L_ex: Exchange influence.
        ci_loop: Confidence interval for ``L_loop`` (lo, hi).
        ci_ex: Confidence interval for ``L_ex`` (lo, hi).
        M_db: Decibel loop-dominance.
        nc1_pass: Whether NC1 was met in this window.
    """

    L_loop: float
    L_ex: float
    ci_loop: Tuple[float, float]
    ci_ex: Tuple[float, float]
    M_db: float
    nc1_pass: bool


class LREG:
    """Enclave-like store for raw L and CI with derived indicators.

    Raw entries are write-only; external callers should use :meth:`derive` to
    access device-signed-style indicators only.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: Dict[int, LEntry] = {}
        self._counter = 0
        self._invalidated = False
        self._reason: Optional[str] = None

    @property
    def invalidated(self) -> bool:
        """Whether the run has been invalidated by a guardrail.

        Returns:
            True if invalidated; otherwise False.
        """
        return self._invalidated

    @property
    def reason(self) -> Optional[str]:
        """Reason code for invalidation, if any.

        Returns:
            Reason string or None.
        """
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
        """Return derived indicators suitable for export.

        Returns:
            Dict containing at minimum:
            - ``nc1``: Boolean NC1 status after invalidation check.
            - ``M_db``: Decibel loop-dominance of latest window.
            - ``counter``: Number of windows written so far.
            - ``invalidated``: Whether the run has been invalidated.
        """
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
