# Mental model

If you only read one page of these docs, read this one. Everything
else either zooms into a piece of this picture or shows you how to
operate it.

## The one-paragraph version

LDTC is a `Δt`-clocked controller wrapped around a plant. Every
window, it estimates how predictable the loop's signals are *from
each other* (`𝓛_loop`) versus how predictable they are *from the
environment* (`𝓛_ex`), takes the decibel ratio
`M = 10 · log₁₀(𝓛_loop / 𝓛_ex)`, and asks two questions: "Is `M`
above `Mmin`?" (NC1) and "After we kick the plant with a labeled
`Ω`, does `M` recover within `τ_max`?" (SC1). The raw measurements
stay locked inside an enclave (`LREG`); only a tiny, signed packet
of derived bits leaves. A hash-chained audit log records every
step. If anything looks fishy (`Δt` was edited too often, the CIs
blew up, the partition flapped under `Ω`), smell tests invalidate
the run before any indicator is signed.

## The actors

| Actor | Code | Job |
| ----- | ---- | --- |
| Scheduler | [`FixedScheduler`][ldtc.runtime.scheduler.FixedScheduler] | Wakes up every `Δt` and runs one tick. |
| Plant | [`Plant`][ldtc.plant.models.Plant] / [`HardwarePlantAdapter`][ldtc.plant.hw_adapter.HardwarePlantAdapter] | The thing being measured: `(E, T, R, demand, io, H)` evolve in time. |
| Controller | [`ControllerPolicy`][ldtc.arbiter.policy.ControllerPolicy] | Reads state, predicts risk, writes actuators. |
| Window buffer | [`SlidingWindow`][ldtc.runtime.windows.SlidingWindow] | Collects `W` samples for the next estimator pass. |
| Estimator | [`estimate_L`][ldtc.lmeas.estimators.estimate_L] | Turns a window into `(𝓛_loop, 𝓛_ex)` with bootstrapped CIs. |
| Partition | [`PartitionManager`][ldtc.lmeas.partition.PartitionManager] | Decides which signals are "loop" vs "exchange," with hysteresis and an `Ω` freeze. |
| LREG | [`LREG`][ldtc.guardrails.lreg.LREG] | Write-only enclave that holds raw `𝓛`; only `derive()` returns sanctioned indicators. |
| Audit | [`AuditLog`][ldtc.guardrails.audit.AuditLog] | Append-only, hash-chained event journal. |
| `Δt` guard | [`DeltaTGuard`][ldtc.guardrails.dt_guard.DeltaTGuard] | Rate-limits and audits `Δt` changes. |
| Smell tests | [`smelltests`][ldtc.guardrails.smelltests] | Invalidate runs that violate measurement hygiene. |
| `Ω` battery | [`omega.power_sag`][ldtc.omega.power_sag], [`omega.ingress_flood`][ldtc.omega.ingress_flood], [`omega.command_conflict`][ldtc.omega.command_conflict] | Apply labeled, time-bounded perturbations. |
| Refusal arbiter | [`RefusalArbiter`][ldtc.arbiter.refusal.RefusalArbiter] | Refuses risky commands when `M < Mmin`; records `T_refuse`. |
| Indicator exporter | [`IndicatorExporter`][ldtc.attest.exporter.IndicatorExporter] | Builds a CBOR payload and Ed25519-signs it. |
| Reporting | [`reporting.artifacts.bundle`][ldtc.reporting.artifacts.bundle] | Renders the timeline figure, SC1 table, and manifest. |

## What each tick does

```text
        ┌──────────────────────────────────────────────────────────┐
        │                       FixedScheduler                     │
        │            wakes every Δt, runs the closure below        │
        └──────────────────────────────────────────────────────────┘
                                     │
                                     ▼
            ┌────────────────────────────────────────────────┐
            │ 1. adapter.read_state()  ──> state dict        │
            │ 2. policy.compute(state, predicted_M_db,       │
            │      risky_cmd) ──> action                     │
            │    └── arbiter.decide() if risky_cmd present   │
            │ 3. adapter.write_actuators(action)             │
            │ 4. window.append(state vector)                 │
            └────────────────────────────────────────────────┘
                                     │
                                     ▼
            ┌────────────────────────────────────────────────┐
            │ 5. if window full:                             │
            │      L = estimate_L(window, partition)         │
            │      M = m_db(L.L_loop, L.L_ex)                │
            │      LREG.write(LEntry(...))                   │
            │      audit.append("window_measured", ...)      │
            │      smell tests: ci_inflation, etc.           │
            └────────────────────────────────────────────────┘
                                     │
                                     ▼
            ┌────────────────────────────────────────────────┐
            │ 6. periodically:                               │
            │      derived = LREG.derive()                   │
            │      exporter.maybe_export(priv, audit,        │
            │                            derived, cfg,       │
            │                            last_sc1_pass)      │
            └────────────────────────────────────────────────┘
```

The scheduler runs the tick closure in a daemon thread, so
keyboard interrupts and the post-run audit checks stay responsive.

## What an `Ω` trial does

An `Ω` handler such as
[`omega.power_sag.apply`][ldtc.omega.power_sag.apply] is just a
*labeled* configuration change to the plant. Around it, the CLI:

1. Records baseline `𝓛_loop` from the previous window.
2. Calls `partition.freeze()` so SC1 cannot be gamed by reshuffling
   `(C, Ex)` mid-perturbation.
3. Appends an `omega_event` audit record with the kind and
   parameters.
4. Lets the scheduler keep ticking; estimators continue to fire
   and the trough of `𝓛_loop` is recorded.
5. After the labeled interval ends, calls `partition.unfreeze()`
   and waits for `𝓛_loop` to recover to
   `baseline · (1 − ε)`. The elapsed time is `τ_rec`.
6. Calls
   [`sc1_evaluate`][ldtc.lmeas.metrics.sc1_evaluate] with
   `(𝓛_loop_baseline, 𝓛_loop_trough, 𝓛_loop_recovered, M_post,
   ε, τ_rec, Mmin, τ_max)`; the boolean result becomes the next
   `SC1` bit.

## What you can quietly tune (and what stops you)

Two pieces of design exist specifically to keep authors from
sneaking past NC1 / SC1:

1. **Raw `𝓛` is locked in LREG.** No public method on
   [`LREG`][ldtc.guardrails.lreg.LREG] returns raw values; the
   sanctioned escape hatch is
   [`derive`][ldtc.guardrails.lreg.LREG.derive], and CSV writers
   plus the indicator builder both run
   [`audit_contains_raw_lreg_values`][ldtc.guardrails.smelltests.audit_contains_raw_lreg_values]
   before emitting anything.
2. **`Δt`, partition, and CI are watched.** Smell tests in
   [`ldtc.guardrails.smelltests`][ldtc.guardrails.smelltests] flag
   `invalid_by_ci`, `invalid_by_partition_flips`,
   `invalid_flip_during_omega`, `audit_chain_broken`, and the
   subsidy red flag. Excessive `Δt` edits are rejected inline by
   the [`DeltaTGuard`][ldtc.guardrails.dt_guard.DeltaTGuard]. Each
   invalidation appends to the audit and forces the next exported
   indicator to carry `invalidated = true`.

This is what we mean by "operational, not metaphysical": the
indicators are bits, but the *protocol* around them is what gives
the bits their meaning.

## How LDTC differs from a generic control loop

| Feature | Generic control loop | LDTC |
| ------- | -------------------- | ---- |
| Time base | Best-effort | Hard-fixed `Δt`, audited changes only. |
| Telemetry sink | Logs / Prometheus | Write-only enclave + signed indicators. |
| Failure mode | Alert / page | Audit `run_invalidated`, signed `invalidated` bit. |
| Metric output | RMS error, set-point | `M (dB)`, `δ`, `τ_rec`, NC1, SC1. |
| Adversary model | None | Operator who would like NC1 / SC1 to come out a particular way. |

If you would not be comfortable claiming the result *because the
loop got to choose its own thresholds, partition, or `Δt` mid-run*,
the harness is doing its job.

## Reading the rest of the docs

- [Lifecycle](lifecycle.md) goes through one CLI invocation
  end-to-end: process startup, scheduler, audit close, artifact
  bundle.
- [Architecture](architecture.md) gives the static module map and
  data-flow diagram.
- [Indicators](indicators.md) describes the wire format and what
  a verifier checks.
- [Guardrails](guardrails.md) enumerates the smell tests with
  their thresholds.
- [Paper-to-code](paper-to-code.md) is the per-section crosswalk
  from the manuscript.
