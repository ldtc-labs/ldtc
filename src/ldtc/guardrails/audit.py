"""Append-only audit log.

Hash-chained JSONL records with monotonic counters used to attest
measurement and policy events. The audit chain provides tamper-evident
provenance for an LDTC run: every record links to the previous record's
SHA-256, so any post-hoc edit invalidates the chain from that point
forward.

See Also:
    `paper/main.tex`: Methods: Measurement and Attestation; Audit chain.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


@dataclass
class AuditRecord:
    """Serialized audit record structure.

    Attributes:
        counter: Monotonic counter for this record. Starts at 1 and
            strictly increases.
        ts: UNIX timestamp (float seconds, from `time.time()`).
        event: Event name (free-form string used for filtering and
            replay).
        details: Arbitrary JSON-serializable details. Policy filters
            block raw LREG keys (`L_loop`, `L_ex`, `ci_loop`, `ci_ex`)
            from leaking through this channel.
        prev_hash: Hash of the previous record (`"GENESIS"` for the
            first).
        hash: SHA-256 hash of this record's canonical JSON.
    """

    counter: int
    ts: float
    event: str
    details: Dict[str, Any]
    prev_hash: str
    hash: str


class AuditLog:
    """Append-only, hash-chained audit log in JSONL format.

    Ensures monotonic counters and a verifiable hash chain across
    records. Used throughout the CLI to record measurement, governance,
    and policy events. Writers are serialized through an internal lock so
    multiple threads can append safely.

    Args:
        path: Filesystem path to the JSONL audit file. The parent
            directory is created if it does not exist.
    """

    def __init__(self, path: str) -> None:
        """Initialize an audit log rooted at `path`.

        Args:
            path: Filesystem path to the JSONL audit file. The parent
                directory is created if it does not exist.
        """
        self.path = path
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._lock = threading.Lock()
        self._counter = 0
        self._prev_hash = "GENESIS"

    def append(self, event: str, details: Optional[Dict[str, Any]] = None) -> AuditRecord:
        """Append an event to the audit log.

        Args:
            event: Event name (free-form, but conventionally
                `snake_case`, e.g., `"scheduler_started"`).
            details: Optional dict of additional fields. Raw LREG keys
                (`L_loop`, `L_ex`, `ci_loop`, `ci_ex`) are blocked by
                policy and will raise [`ValueError`][].

        Returns:
            The [`AuditRecord`][ldtc.guardrails.audit.AuditRecord] that
            was written.

        Raises:
            ValueError: If `details` contains any raw LREG key.
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
        """Hex-encoded SHA-256 of the most recently written record.

        Equals `"GENESIS"` until the first record is written. Use this
        to anchor downstream artifacts (e.g., signed indicator
        manifests) to a specific run.
        """
        return self._prev_hash

    @property
    def counter(self) -> int:
        """Monotonic counter of the last record written (0 before any writes)."""
        return self._counter
