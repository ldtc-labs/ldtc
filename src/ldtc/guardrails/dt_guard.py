"""Guardrails: Δt governance.

Privileged, rate-limited interface to mutate scheduler Δt with audit logging
and run invalidation on policy violations.

See Also:
    paper/main.tex — Smell-tests & invalidation; Δt governance.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional, Dict, Any

from .audit import AuditLog


@dataclass
class DtGuardConfig:
    """Configuration for Δt governance constraints.

    Attributes:
        max_changes_per_hour: Maximum permitted changes in any rolling hour.
        min_seconds_between_changes: Minimum spacing between edits.
    """

    max_changes_per_hour: int = 3
    min_seconds_between_changes: float = 1.0


class DeltaTGuard:
    """Privileged Δt governance wrapper.

    Single, rate-limited pathway to update scheduler Δt with audit records and
    invalidation signaling when limits are exceeded.

    Args:
        audit: AuditLog instance used for recording events.
        cfg: Optional configuration for rate limits.
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
        """Check whether a Δt change is permissible.

        Args:
            now: Optional timestamp override for rate-limit accounting.

        Returns:
            True if within hourly and spacing limits; otherwise False.
        """
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
        """Attempt to change Δt; audit and invalidate on violations.

        Args:
            scheduler: Object exposing ``set_dt(new_dt) -> old_dt``.
            new_dt: Desired new Δt in seconds.
            policy_digest: Optional identifier of the policy authorizing the change.

        Returns:
            True if the change was committed; False if refused and the run was
            invalidated by audit.
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
        """Whether a Δt governance violation invalidated the run.

        Returns:
            True if invalidated; otherwise False.
        """
        return self._invalidated
