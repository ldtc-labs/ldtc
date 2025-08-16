from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional, Dict, Any

from .audit import AuditLog


@dataclass
class DtGuardConfig:
    max_changes_per_hour: int = 3
    min_seconds_between_changes: float = 1.0


class DeltaTGuard:
    """
    Privileged Δt governance:
    - Single API to change Δt
    - Appends audit records (old/new/policy digest placeholder)
    - Monotonic counter is provided by AuditLog
    - Rate-limits changes; emits invalidation events on violations
    """

    def __init__(self, audit: AuditLog, cfg: Optional[DtGuardConfig] = None) -> None:
        self.audit = audit
        self.cfg = cfg or DtGuardConfig()
        self._last_change_ts: Optional[float] = None
        self._window_start_ts: float = time.time()
        self._changes_in_window: int = 0
        self._invalidated: bool = False

    def _reset_window_if_needed(self, now: float) -> None:
        if (now - self._window_start_ts) >= 3600.0:
            self._window_start_ts = now
            self._changes_in_window = 0

    def can_change(self, now: Optional[float] = None) -> bool:
        now = now or time.time()
        self._reset_window_if_needed(now)
        if self._changes_in_window >= self.cfg.max_changes_per_hour:
            return False
        if (
            self._last_change_ts is not None
            and (now - self._last_change_ts) < self.cfg.min_seconds_between_changes
        ):
            return False
        return True

    def change_dt(
        self, scheduler: Any, new_dt: float, policy_digest: Optional[str] = None
    ) -> bool:
        """
        The only supported way to change Δt. Returns True if committed; False if refused
        and an invalidation audit event was written.
        """
        now = time.time()
        self._reset_window_if_needed(now)

        if not self.can_change(now):
            # Violation -> invalidate run (assay) and refuse change
            self.audit.append(
                "run_invalidated",
                {
                    "reason": "dt_change_rate_limit",
                    "changes_this_hour": self._changes_in_window,
                    "min_gap_s": self.cfg.min_seconds_between_changes,
                    "reason_human": "Δt edit rate exceeded (limit 3/hour and min spacing enforced)",
                },
            )
            self._invalidated = True
            return False

        getattr(scheduler, "dt", None)
        prev = scheduler.set_dt(new_dt)
        # prev is the same as old_dt; log audit
        details: Dict[str, Any] = {
            "old_dt": prev,
            "new_dt": new_dt,
        }
        if policy_digest:
            details["policy_digest"] = policy_digest
        self.audit.append("dt_changed", details)

        # Update counters
        self._last_change_ts = now
        self._changes_in_window += 1
        return True

    @property
    def invalidated(self) -> bool:
        return self._invalidated
