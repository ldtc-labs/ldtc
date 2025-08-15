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
    counter: int
    ts: float
    event: str
    details: Dict[str, Any]
    prev_hash: str
    hash: str


class AuditLog:
    """
    Append-only, hash-chained audit log (JSONL).
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
        return self._prev_hash

    @property
    def counter(self) -> int:
        return self._counter
