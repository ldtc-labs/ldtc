"""Δt governance.

A privileged, rate-limited interface for mutating the scheduler's `Δt`.
Records every accepted change in the audit log and invalidates the run
when policy limits are exceeded. The intent is to prevent operators from
"tuning" away an SC1 violation by changing the sample rate mid-run.

See Also:
    `paper/main.tex`: Smell-tests and invalidation; Δt governance.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .audit import AuditLog


@dataclass
class DtGuardConfig:
    """Configuration for `Δt` governance constraints.

    Attributes:
        max_changes_per_hour: Maximum permitted changes in any rolling
            one-hour window.
        min_seconds_between_changes: Minimum wall-clock spacing between
            consecutive edits, in seconds.
    """

    max_changes_per_hour: int = 3
    min_seconds_between_changes: float = 1.0


class DeltaTGuard:
    """Privileged `Δt` governance wrapper.

    The single, rate-limited pathway to update the scheduler's `Δt`.
    Every accepted change is recorded in the audit log; every refused
    change invalidates the run by appending a `run_invalidated` event
    with the human-readable reason.

    Args:
        audit: [`AuditLog`][ldtc.guardrails.audit.AuditLog] instance used
            for recording events.
        cfg: Optional configuration for rate limits. Defaults to a
            sensible policy of 3 changes / hour with at least 1 s between
            changes.
    """

    def __init__(self, audit: AuditLog, cfg: Optional[DtGuardConfig] = None) -> None:
        """Initialize the guard. See class docstring for argument details."""
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
        """Check whether a `Δt` change is currently permissible.

        Args:
            now: Optional timestamp override (unix seconds) for
                rate-limit accounting. Tests use this to simulate the
                passage of time.

        Returns:
            `True` if within both hourly and spacing limits; otherwise
            `False`.
        """
        now = now or time.time()
        self._reset_window_if_needed(now)
        if self._changes_in_window >= self.cfg.max_changes_per_hour:
            return False
        if self._last_change_ts is not None and (now - self._last_change_ts) < self.cfg.min_seconds_between_changes:
            return False
        return True

    def change_dt(self, scheduler: Any, new_dt: float, policy_digest: Optional[str] = None) -> bool:
        """Attempt to change `Δt`; audit and invalidate on violations.

        Args:
            scheduler: Object exposing `set_dt(new_dt) -> old_dt`,
                typically a [`FixedScheduler`][ldtc.runtime.scheduler.FixedScheduler].
            new_dt: Desired new `Δt` in seconds.
            policy_digest: Optional identifier of the policy that
                authorized the change. Recorded in the audit details.

        Returns:
            `True` if the change was committed; `False` if it was
            refused (the run is invalidated in that case).
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
        """`True` once a `Δt` governance violation has invalidated the run."""
        return self._invalidated
