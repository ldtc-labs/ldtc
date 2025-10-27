"""Guardrails: Append-only audit log.

Hash-chained JSONL records with monotonic counters used to attest measurement
and policy events, providing tamper-evident provenance for runs.

See Also:
    paper/main.tex — Methods: Measurement & Attestation; Audit chain.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional


@dataclass
class AuditRecord:
    """Serialized audit record structure.

    Attributes:
        counter: Monotonic counter for this record.
        ts: UNIX timestamp (float seconds).
        event: Event name.
        details: Arbitrary JSON-serializable details (policy filters applied).
        prev_hash: Hash of the previous record ("GENESIS" for the first).
        hash: SHA-256 hash of this record's canonical JSON.
    """

    counter: int
    ts: float
    event: str
    details: Dict[str, Any]
    prev_hash: str
    hash: str


class AuditLog:
    """Append-only, hash-chained audit log (JSONL).

    Ensures monotonic counters and a verifiable hash chain across records. Used
    throughout the CLI to record measurement and governance events.

    Args:
        path: Filesystem path to the JSONL audit file.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._lock = threading.Lock()
        self._counter = 0
        self._prev_hash = "GENESIS"

    def append(
        self, event: str, details: Optional[Dict[str, Any]] = None
    ) -> AuditRecord:
        """Append an event to the audit log.

        Args:
            event: Event name.
            details: Optional dict of additional fields; raw LREG keys are
                blocked by policy and will raise an error.

        Returns:
            The :class:`AuditRecord` that was written.
        """
        with self._lock:
            self._counter += 1
            ts = time.time()
            details = details or {}
            # Defense-in-depth: block raw LREG leakage via audit details
            banned = {"L_loop", "L_ex", "ci_loop", "ci_ex"}
            if any(k in details for k in banned):
                raise ValueError("raw LREG fields are not permitted in audit details")
            raw = json.dumps(
                {
                    "counter": self._counter,
                    "ts": ts,
                    "event": event,
                    "details": details,
                    "prev_hash": self._prev_hash,
                },
                sort_keys=True,
            )
            h = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            rec = AuditRecord(
                counter=self._counter,
                ts=ts,
                event=event,
                details=details,
                prev_hash=self._prev_hash,
                hash=h,
            )
            self._prev_hash = h
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(rec), sort_keys=True) + "\n")
            return rec

    @property
    def last_hash(self) -> str:
        """Return the current hash head of the audit chain.

        Returns:
            Hex-encoded hash string.
        """
        return self._prev_hash

    @property
    def counter(self) -> int:
        """Return the last written counter value.

        Returns:
            Monotonic counter for the last record written.
        """
        return self._counter
