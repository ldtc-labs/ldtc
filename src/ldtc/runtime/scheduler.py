"""Fixed-interval scheduler.

A lightweight Δt-enforcing scheduler with jitter metrics and optional
audit hooks. Used by CLI runs and the verification harness loops to
guarantee that measurements happen on a stable cadence regardless of
estimator runtime.

The scheduler runs the user-provided tick callback in a daemon thread,
so the caller stays responsive (for example, to handle keyboard
interrupts) while ticks fire in the background. Jitter is recorded per
tick and exposed via `stats.jitter_*` properties so that the
[`dt_guard`][ldtc.guardrails.dt_guard] can decide whether the current
schedule is still healthy.

See Also:
    `paper/main.tex`: Methods: Measurement and Attestation Guardrails.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional


@dataclass
class TickStats:
    """Per-run jitter and tick counters for a [`FixedScheduler`][ldtc.runtime.scheduler.FixedScheduler].

    Attributes:
        dt_target: Target tick period in seconds.
        ticks: Number of ticks recorded so far.
        jitter_abs_sum: Sum of `|actual_dt - dt_target|` over all ticks.
        jitter_max: Largest absolute jitter observed.
        start_time: `perf_counter()` value captured at construction.
        jitters: Per-tick absolute jitter samples, kept for percentile
            queries.
    """

    dt_target: float
    ticks: int = 0
    jitter_abs_sum: float = 0.0
    jitter_max: float = 0.0
    start_time: float = field(default_factory=time.perf_counter)
    jitters: list[float] = field(default_factory=list)

    def record(self, actual_dt: float) -> None:
        """Record a single tick's actual interval.

        Args:
            actual_dt: Measured interval in seconds since the previous tick.
        """
        self.ticks += 1
        jitter = abs(actual_dt - self.dt_target)
        self.jitter_abs_sum += jitter
        if jitter > self.jitter_max:
            self.jitter_max = jitter
        self.jitters.append(jitter)

    @property
    def elapsed(self) -> float:
        """Wall-clock seconds since the scheduler started."""
        return time.perf_counter() - self.start_time

    @property
    def jitter_mean_abs(self) -> float:
        """Mean absolute jitter across all recorded ticks."""
        return (self.jitter_abs_sum / self.ticks) if self.ticks else 0.0

    def jitter_percentile_abs(self, q: float = 0.95) -> float:
        """Nearest-rank percentile of the absolute jitter distribution.

        Args:
            q: Percentile in `[0, 1]`. Values outside the range are
                clamped.

        Returns:
            The `q`-th percentile of `|actual_dt - dt_target|`, in
            seconds. Returns `0.0` if no ticks have been recorded yet.
        """
        if not self.jitters:
            return 0.0
        q = 0.0 if q < 0.0 else (1.0 if q > 1.0 else q)
        js = sorted(self.jitters)
        k = max(0, min(len(js) - 1, int(round(q * (len(js) - 1)))))
        return js[k]

    @property
    def jitter_p95_abs(self) -> float:
        """Convenience alias for `jitter_percentile_abs(0.95)`."""
        return self.jitter_percentile_abs(0.95)


class FixedScheduler:
    """Fixed-interval scheduler.

    Enforces a constant sampling interval `Δt` and invokes a tick
    callback every period until stopped. Tracks jitter statistics and
    emits optional audit events through a user-provided hook.

    Args:
        dt: Target period in seconds (`Δt > 0`).
        tick_fn: Callback invoked each tick with the current
            `perf_counter` timestamp.
        on_start: Optional hook executed before the worker thread begins.
        on_stop: Optional hook executed after stop; receives the final
            [`TickStats`][ldtc.runtime.scheduler.TickStats].
        audit_hook: Optional callable taking `(event: str, details: Dict)`
            for emitting audit records (typically wired up to
            [`AuditLog.append`][ldtc.guardrails.audit.AuditLog.append]).

    Notes:
        - Jitter metrics are accessible on the `stats` attribute after
          ticks have been recorded.
        - Thread-safe updates to `Δt` can be made via `set_dt`. The new
          period takes effect at the *next* tick boundary.
    """

    def __init__(
        self,
        dt: float,
        tick_fn: Callable[[float], None],
        on_start: Optional[Callable[[], None]] = None,
        on_stop: Optional[Callable[[TickStats], None]] = None,
        audit_hook: Optional[Callable[[str, Dict], None]] = None,
    ) -> None:
        """Initialize the scheduler. See class docstring for argument details."""
        assert dt > 0.0
        self.dt = dt
        self.tick_fn = tick_fn
        self.on_start = on_start
        self.on_stop = on_stop
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.stats = TickStats(dt_target=dt)
        self.audit = audit_hook
        self._dt_lock = threading.Lock()
        self._scripted: list[Dict] = []
        self._dt_guard: Any = None

    def set_scripted(self, scripted: Optional[list], dt_guard: Any) -> None:
        """Register scripted `Δt` changes applied from a background thread.

        Mirrors [`SimDriver.set_scripted`][ldtc.runtime.sim.SimDriver.set_scripted]
        so the two drivers are interchangeable. The changes are applied at
        their `at_sec` offsets (wall-clock) once `start` is called.

        Args:
            scripted: Sequence of `{at_sec, new_dt, policy_digest?}` items.
            dt_guard: Governance guard through which changes are routed.
        """
        self._scripted = list(scripted or [])
        self._dt_guard = dt_guard

    def run_for(self, sim_seconds: float) -> None:
        """Block for a wall-clock duration while ticks fire in the worker.

        Provided so call sites can use the same `run_for` API as
        [`SimDriver`][ldtc.runtime.sim.SimDriver].

        Args:
            sim_seconds: Seconds to block the calling thread.
        """
        time.sleep(max(0.0, float(sim_seconds)))

    def start(self) -> None:
        """Start the worker thread.

        No-op if a worker is already running. Calls `on_start` (if
        provided) before the thread begins, and emits a
        `scheduler_started` audit event.
        """
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="ldtc-scheduler", daemon=True)
        if self.on_start:
            self.on_start()
        if self.audit:
            self.audit("scheduler_started", {"dt": self.dt})
        self._thread.start()
        if self._scripted and self._dt_guard is not None:
            threading.Thread(target=self._run_scripted, name="ldtc-dt-script", daemon=True).start()

    def _run_scripted(self) -> None:
        t0 = time.time()
        for item in self._scripted:
            when = float(item.get("at_sec", 0.0))
            new_dt = float(item["new_dt"])
            pdig = str(item.get("policy_digest", "")) or None
            while (time.time() - t0) < when and not self._stop.is_set():
                time.sleep(0.01)
            if self._stop.is_set():
                return
            self._dt_guard.change_dt(scheduler=self, new_dt=new_dt, policy_digest=pdig)

    def stop(self) -> TickStats:
        """Stop the worker thread and return final stats.

        Joins the worker thread, calls `on_stop` (if provided), and emits
        a `scheduler_stopped` audit event with the summarized jitter
        metrics.

        Returns:
            The final [`TickStats`][ldtc.runtime.scheduler.TickStats] for
            the run.
        """
        self._stop.set()
        if self._thread:
            self._thread.join()
        if self.on_stop:
            self.on_stop(self.stats)
        if self.audit:
            self.audit(
                "scheduler_stopped",
                {
                    "ticks": self.stats.ticks,
                    "elapsed": self.stats.elapsed,
                    "jitter_max": self.stats.jitter_max,
                    "jitter_mean_abs": self.stats.jitter_mean_abs,
                    "jitter_p95_abs": self.stats.jitter_p95_abs,
                    "jitter_p95_rel": ((self.stats.jitter_p95_abs / self.dt) if self.dt > 0 else 0.0),
                },
            )
        return self.stats

    def _run(self) -> None:
        next_t = time.perf_counter()
        while not self._stop.is_set():
            now = time.perf_counter()
            if now >= next_t:
                self.tick_fn(now)
                with self._dt_lock:
                    cur_dt = self.dt
                actual_dt = time.perf_counter() - next_t + cur_dt
                self.stats.record(actual_dt)
                next_t += cur_dt
                if next_t < time.perf_counter():
                    next_t = time.perf_counter() + cur_dt
            else:
                time.sleep(max(0.0, next_t - now))

    def set_dt(self, new_dt: float) -> float:
        """Change `Δt` at runtime in a thread-safe way.

        The new period is applied at the next tick boundary, so a tick
        currently in flight finishes against the previous interval.

        Args:
            new_dt: New period in seconds (`Δt > 0`).

        Returns:
            The previous `dt` value.
        """
        assert new_dt > 0.0
        with self._dt_lock:
            old = self.dt
            self.dt = new_dt
            self.stats.dt_target = new_dt
        if self.audit:
            self.audit("scheduler_dt_updated", {"old_dt": old, "new_dt": new_dt})
        return old
