# ldtc.runtime

Fixed-`Δt` real-time loop primitives. Two pieces:

- [`scheduler`](#scheduler): a daemon-thread `FixedScheduler`
  that runs a tick callback every `Δt` seconds and tracks per-
  tick jitter for the [`Δt` guard][ldtc.guardrails.dt_guard].
- [`windows`](#windows): a `SlidingWindow` ring buffer that
  collects state vectors for the next [estimator][ldtc.lmeas]
  pass.

Together these define the harness's heartbeat. The CLI
constructs both and hands them to the run loop in
[`run_baseline`][ldtc.cli.main.run_baseline].

::: ldtc.runtime
    options:
      members: false
      show_root_heading: false
      show_source: false

## scheduler

::: ldtc.runtime.scheduler

## windows

::: ldtc.runtime.windows
