"""Runtime utilities for fixed-interval scheduling and sliding windows.

`runtime` provides the small mechanical pieces that LDTC's verification
loops are built on:

- [`scheduler`][ldtc.runtime.scheduler] exposes
  [`FixedScheduler`][ldtc.runtime.scheduler.FixedScheduler], a
  Δt-enforcing scheduler with jitter metrics and audit hooks.
- [`windows`][ldtc.runtime.windows] exposes
  [`SlidingWindow`][ldtc.runtime.windows.SlidingWindow] for per-channel
  telemetry buffering and `block_bootstrap_indices` for CI estimation.

These primitives are intentionally tiny and decoupled. They have no
knowledge of NC1 or SC1; they exist so that the CLI run loop can stream
telemetry into the [`lmeas`][ldtc.lmeas] estimators on a stable cadence.
"""
