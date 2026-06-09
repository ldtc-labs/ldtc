"""Deterministic simulation driver.

A drop-in alternative to [`FixedScheduler`][ldtc.runtime.scheduler.FixedScheduler]
for in-process simulation runs. Instead of firing ticks on the wall clock
in a background thread, the [`SimDriver`][ldtc.runtime.sim.SimDriver]
advances simulated time in fixed `Δt` steps synchronously, calling the
tick callback once per step with a simulated timestamp.

This matters for reproducibility and validity. The verification harness
does heavy per-window work (bootstrap CIs, stationarity diagnostics), and
on a real clock that work makes a small `Δt` unachievable, producing large
scheduler jitter that (correctly) invalidates the run. For a pure
simulation that jitter is an artifact of running the model slower than
real time, not a property of the system under test. Driving the
simulation deterministically removes the artifact: every tick lands
exactly on its `Δt` boundary, so jitter is zero by construction and the
results depend only on the seeds, not on how fast the host happens to be.

Use [`make_driver`][ldtc.runtime.sim.make_driver] to select a driver from
a profile: software/simulation profiles get a `SimDriver`; profiles that
opt into real-time execution (`realtime: true`) or drive hardware get a
[`FixedScheduler`][ldtc.runtime.scheduler.FixedScheduler].

See Also:
    `paper/main.tex`: Methods: Measurement and Attestation; Reproducibility.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence

from .scheduler import FixedScheduler, TickStats


class SimDriver:
    """Deterministic, wall-clock-free driver with a scheduler-like API.

    Exposes the subset of the
    [`FixedScheduler`][ldtc.runtime.scheduler.FixedScheduler] interface the
    CLI relies on (`start`, `run_for`, `stop`, `set_dt`, `stats`) so the two
    are interchangeable. Ticks are executed synchronously in
    [`run_for`][ldtc.runtime.sim.SimDriver.run_for]; each records exactly
    `Δt` as its interval, so the reported jitter is always zero.

    Args:
        dt: Simulated tick period in seconds (`Δt > 0`).
        tick_fn: Callback invoked each step with the simulated timestamp.
        audit_hook: Optional callable taking `(event, details)` for
            emitting audit records, mirroring `FixedScheduler`.
    """

    def __init__(
        self,
        dt: float,
        tick_fn: Callable[[float], None],
        audit_hook: Optional[Callable[[str, Dict], None]] = None,
    ) -> None:
        """Initialize the driver. See class docstring for argument details."""
        assert dt > 0.0
        self.dt = dt
        self.tick_fn = tick_fn
        self.audit = audit_hook
        self.stats = TickStats(dt_target=dt)
        self.now_sim = 0.0
        self._scripted: List[Dict[str, Any]] = []
        self._dt_guard: Any = None
        self._applied: set[int] = set()

    def set_scripted(self, scripted: Optional[Sequence[Dict[str, Any]]], dt_guard: Any) -> None:
        """Register scripted `Δt` changes to apply during the run.

        Args:
            scripted: Sequence of items, each with `at_sec`, `new_dt`, and
                optional `policy_digest`. Applied (in simulated time) the
                first time `now_sim` reaches each item's `at_sec`.
            dt_guard: The [`DeltaTGuard`][ldtc.guardrails.dt_guard.DeltaTGuard]
                through which changes are routed (so governance limits and
                audit records are exercised exactly as in real time).
        """
        self._scripted = list(scripted or [])
        self._dt_guard = dt_guard
        self._applied = set()

    def start(self) -> None:
        """Emit the `scheduler_started` audit event (no thread is spawned)."""
        if self.audit:
            self.audit("scheduler_started", {"dt": self.dt})

    def _maybe_apply_scheduled(self) -> None:
        if not self._scripted or self._dt_guard is None:
            return
        for i, item in enumerate(self._scripted):
            if i in self._applied:
                continue
            if self.now_sim >= float(item.get("at_sec", 0.0)):
                new_dt = float(item["new_dt"])
                pdig = str(item.get("policy_digest", "")) or None
                self._dt_guard.change_dt(scheduler=self, new_dt=new_dt, policy_digest=pdig)
                self._applied.add(i)

    def run_for(self, sim_seconds: float) -> None:
        """Advance the simulation by a duration, firing ticks each `Δt`.

        Args:
            sim_seconds: Simulated duration to advance. The number of ticks
                is `round(sim_seconds / Δt)`.
        """
        if self.dt <= 0.0:
            return
        n = int(round(max(0.0, float(sim_seconds)) / self.dt))
        for _ in range(n):
            self._maybe_apply_scheduled()
            self.tick_fn(self.now_sim)
            self.stats.record(self.dt)  # actual == target -> zero jitter
            self.now_sim += self.dt

    def set_dt(self, new_dt: float) -> float:
        """Change `Δt`, returning the previous value.

        Args:
            new_dt: New simulated period in seconds (`Δt > 0`).

        Returns:
            The previous `dt`.
        """
        assert new_dt > 0.0
        old = self.dt
        self.dt = new_dt
        self.stats.dt_target = new_dt
        if self.audit:
            self.audit("scheduler_dt_updated", {"old_dt": old, "new_dt": new_dt})
        return old

    def stop(self) -> TickStats:
        """Emit the `scheduler_stopped` audit event and return final stats.

        Returns:
            The final [`TickStats`][ldtc.runtime.scheduler.TickStats]; jitter
            metrics are zero by construction.
        """
        if self.audit:
            self.audit(
                "scheduler_stopped",
                {
                    "ticks": self.stats.ticks,
                    "elapsed": self.now_sim,
                    "jitter_max": self.stats.jitter_max,
                    "jitter_mean_abs": self.stats.jitter_mean_abs,
                    "jitter_p95_abs": self.stats.jitter_p95_abs,
                    "jitter_p95_rel": 0.0,
                },
            )
        return self.stats


def make_driver(
    prof: Dict[str, Any],
    dt: float,
    tick_fn: Callable[[float], None],
    audit_hook: Optional[Callable[[str, Dict], None]] = None,
    dt_guard: Any = None,
) -> Any:
    """Select and build a driver from a profile.

    Returns a deterministic [`SimDriver`][ldtc.runtime.sim.SimDriver] for
    in-process simulation profiles (the default), or a real-time
    [`FixedScheduler`][ldtc.runtime.scheduler.FixedScheduler] when the
    profile opts in (`realtime: true`) or targets a hardware adapter. Any
    `scripted_dt_changes` in the profile are registered on the driver.

    Args:
        prof: Loaded YAML profile dict.
        dt: Target period in seconds.
        tick_fn: Per-tick callback.
        audit_hook: Optional audit hook.
        dt_guard: Optional `Δt` governance guard for scripted changes.

    Returns:
        A driver exposing `start`, `run_for`, `stop`, `set_dt`, and
        `stats`.
    """
    realtime = bool(prof.get("realtime", False))
    plant_prof = prof.get("plant", {}) or {}
    adapter_kind = str(plant_prof.get("adapter", "sim")).lower()
    scripted = prof.get("scripted_dt_changes", [])
    use_sim = (not realtime) and adapter_kind in ("sim", "software", "inproc")
    if use_sim:
        drv = SimDriver(dt=dt, tick_fn=tick_fn, audit_hook=audit_hook)
        drv.set_scripted(scripted, dt_guard)
        return drv
    sch = FixedScheduler(dt=dt, tick_fn=tick_fn, audit_hook=audit_hook)
    sch.set_scripted(scripted, dt_guard)
    return sch
