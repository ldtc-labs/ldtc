# ldtc.runtime

Fixed-`Δt` real-time loop primitives. Three pieces:

- [`scheduler`](#scheduler): a daemon-thread `FixedScheduler`
  that runs a tick callback every `Δt` seconds and tracks per-
  tick jitter for the [`Δt` guard][ldtc.guardrails.dt_guard].
- [`sim`](#sim): a deterministic, wall-clock-free
  [`SimDriver`][ldtc.runtime.sim.SimDriver] exposing the same API as
  the scheduler, used for reproducible in-process simulation runs.
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

## sim

::: ldtc.runtime.sim

## windows

::: ldtc.runtime.windows
