"""LREG: enclave-like register for raw 𝓛 and CI bounds.

`LREG` ("loop register") holds the per-window raw loop / exchange
influence values and their CIs in memory. By design, raw entries are
write-only from outside the package: external callers go through
[`derive`][ldtc.guardrails.lreg.LREG.derive], which returns only
indicator-grade summaries (`nc1`, `M_db`, counters, invalidation flag).
This honors LDTC's no-raw-LREG export policy: the only thing that ever
leaves the enclave is the derived, device-signed indicator.

See Also:
    `paper/main.tex`: Methods: Measurement and Attestation; Export
    policy.
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
        ci_loop: 95% confidence interval for `L_loop` as `(lo, hi)`.
        ci_ex: 95% confidence interval for `L_ex` as `(lo, hi)`.
        M_db: Decibel loop-dominance for this window.
        nc1_pass: Whether NC1 was met in this window.
    """

    L_loop: float
    L_ex: float
    ci_loop: Tuple[float, float]
    ci_ex: Tuple[float, float]
    M_db: float
    nc1_pass: bool


class LREG:
    """Enclave-like store for raw `𝓛` and CI bounds with derived indicators.

    Raw entries are write-only from outside the package; external
    callers should go through [`derive`][ldtc.guardrails.lreg.LREG.derive]
    to access only the indicator-grade summary. Maintaining this
    boundary is what gives LDTC's exported indicators their integrity
    story.
    """

    def __init__(self) -> None:
        """Initialize an empty LREG with a fresh counter and lock."""
        self._lock = threading.Lock()
        self._entries: Dict[int, LEntry] = {}
        self._counter = 0
        self._invalidated = False
        self._reason: Optional[str] = None

    @property
    def invalidated(self) -> bool:
        """`True` once any guardrail has invalidated this run."""
        return self._invalidated

    @property
    def reason(self) -> Optional[str]:
        """Reason code for the most recent invalidation, or `None`."""
        return self._reason

    def write(self, entry: LEntry) -> int:
        """Append a raw entry and return its sequence index.

        Args:
            entry: Raw [`LEntry`][ldtc.guardrails.lreg.LEntry] for the
                current window.

        Returns:
            Zero-based sequence index assigned to the entry.
        """
        with self._lock:
            idx = self._counter
            self._entries[idx] = entry
            self._counter += 1
            return idx

    def invalidate(self, reason: str) -> None:
        """Mark the run invalidated with a short reason code.

        Subsequent calls to [`derive`][ldtc.guardrails.lreg.LREG.derive]
        will report `invalidated=True` and force `nc1=False`.

        Args:
            reason: Short, machine-readable reason (e.g.,
                `"ci_inflation"`).
        """
        with self._lock:
            self._invalidated = True
            self._reason = reason

    def latest(self) -> Optional[LEntry]:
        """Return the most recently written entry, or `None` if empty."""
        with self._lock:
            if not self._entries:
                return None
            return self._entries[max(self._entries.keys())]

    def derive(self) -> Dict[str, float | int | bool]:
        """Return derived indicators suitable for export.

        This is the *only* read API intended for external callers. The
        returned dict never contains raw `L_loop` / `L_ex` / CI fields,
        and `nc1` is forced `False` when the run has been invalidated.

        Returns:
            Dict with at minimum:

            - `nc1`: Boolean NC1 status after invalidation check.
            - `M_db`: Decibel loop-dominance of the latest window.
            - `counter`: Number of windows written so far.
            - `invalidated`: Whether the run has been invalidated.
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
