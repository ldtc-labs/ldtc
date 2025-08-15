from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional, Dict


@dataclass
class TickStats:
    dt_target: float
    ticks: int = 0
    jitter_abs_sum: float = 0.0
    jitter_max: float = 0.0
    start_time: float = field(default_factory=time.perf_counter)
    jitters: list[float] = field(default_factory=list)

    def record(self, actual_dt: float) -> None:
        self.ticks += 1
        jitter = abs(actual_dt - self.dt_target)
        self.jitter_abs_sum += jitter
        if jitter > self.jitter_max:
            self.jitter_max = jitter
        self.jitters.append(jitter)

    @property
    def elapsed(self) -> float:
        return time.perf_counter() - self.start_time

    @property
    def jitter_mean_abs(self) -> float:
        return (self.jitter_abs_sum / self.ticks) if self.ticks else 0.0

    def jitter_percentile_abs(self, q: float = 0.95) -> float:
        if not self.jitters:
            return 0.0
        # clamp q to [0,1]
        q = 0.0 if q < 0.0 else (1.0 if q > 1.0 else q)
        js = sorted(self.jitters)
        # nearest-rank method
        k = max(0, min(len(js) - 1, int(round(q * (len(js) - 1)))))
        return js[k]

    @property
    def jitter_p95_abs(self) -> float:
        return self.jitter_percentile_abs(0.95)


class FixedScheduler:
    """
    Fixed-interval scheduler that enforces Δt using perf_counter sleep.
    Calls `tick_fn(now)` every Δt seconds until `stop()` is invoked.

    - Records jitter metrics.
    - Provides hooks for 'on_start' and 'on_stop'.
    """

    def __init__(
        self,
        dt: float,
        tick_fn: Callable[[float], None],
        on_start: Optional[Callable[[], None]] = None,
        on_stop: Optional[Callable[[TickStats], None]] = None,
        audit_hook: Optional[Callable[[str, Dict], None]] = None,
    ) -> None:
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

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="ldtc-scheduler", daemon=True
        )
        if self.on_start:
            self.on_start()
        if self.audit:
            self.audit("scheduler_started", {"dt": self.dt})
        self._thread.start()

    def stop(self) -> TickStats:
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
                    "jitter_p95_rel": (
                        (self.stats.jitter_p95_abs / self.dt) if self.dt > 0 else 0.0
                    ),
                },
            )
        return self.stats

    def _run(self) -> None:
        next_t = time.perf_counter()
        while not self._stop.is_set():
            now = time.perf_counter()
            if now >= next_t:
                # tick
                self.tick_fn(now)
                # measure jitter on the tick-to-tick interval
                with self._dt_lock:
                    cur_dt = self.dt
                actual_dt = time.perf_counter() - next_t + cur_dt
                self.stats.record(actual_dt)
                # schedule next
                next_t += cur_dt
                # if we fell behind a lot, jump to now+dt
                if next_t < time.perf_counter():
                    next_t = time.perf_counter() + cur_dt
            else:
                # sleep until next tick
                time.sleep(max(0.0, next_t - now))

    def set_dt(self, new_dt: float) -> float:
        """
        Change the enforced Δt at runtime in a thread-safe way.

        Returns the previous dt.
        """
        assert new_dt > 0.0
        with self._dt_lock:
            old = self.dt
            self.dt = new_dt
            self.stats.dt_target = new_dt
        if self.audit:
            self.audit("scheduler_dt_updated", {"old_dt": old, "new_dt": new_dt})
        return old
