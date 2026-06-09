# LDTC

LDTC (Loop-Dominance Theory of Consciousness) is a single-machine,
real-time verification harness for the theory of the same name. It is
the reference implementation that accompanies the LDTC manuscript and
is designed to either *falsify* or *accept* the two operational
criteria from that paper:

| Criterion | Plain English | Pass when |
| --------- | ------------- | --------- |
| **NC1** | The closed loop dominates exchange with the environment. | `M (dB) ≥ Mmin` window-by-window. |
| **SC1** | The loop's `M` survives a labeled `Ω` perturbation and recovers fast enough. | `δ ≤ ε` and `τ_rec ≤ τ_max` after the `Ω` window. |

The harness measures loop and exchange influence (`𝓛_loop`, `𝓛_ex`)
at a fixed `Δt`, applies guardrails (LREG enclave, hash-chained
audit, `Δt` governance, smell tests), runs `Ω` perturbations from
[`ldtc.omega`][ldtc.omega], and emits **device-signed derived
indicators**, never raw `𝓛`. Everything else (figures, tables,
manifests) is generated from the audit log alone, so you can publish
artifacts without leaking measurement primitives.

The accompanying manuscript validates these criteria in a fully
reproducible, multi-seed simulation study: a positive control, two
structurally distinct negative controls, an exogenous-subsidy
control, an SC1 perturbation battery, and a command-refusal trial.
The criterion separates the controls cleanly and the guardrails
behave as designed. See [Study and results](guides/study.md) to
reproduce every figure and table.

!!! note "What this is, and isn't"
    LDTC is a **verification harness**, not a model of mind. It
    answers a narrow, falsifiable question: "Does this concrete
    system, instrumented at this `Δt`, pass NC1 and SC1 against
    `Ω`?" It does not claim consciousness; it gives you a tool to
    check whether the loop-dominance signature holds.

## Try it in 60 seconds

The smallest end-to-end run uses the bundled R0 profile and the
in-process software plant:

```bash
pip install ldtc
ldtc run --config configs/profile_r0.yml
```

That command will:

1. Boot a fixed-`Δt` scheduler and a small software plant
   ([`ldtc.plant.models.Plant`][ldtc.plant.models.Plant]).
2. Stream `(E, T, R, demand, io, H)` telemetry into a
   [`SlidingWindow`][ldtc.runtime.windows.SlidingWindow].
3. Per window, estimate `𝓛_loop` and `𝓛_ex` via
   [`estimate_L`][ldtc.lmeas.estimators.estimate_L] and compute
   `M (dB)` via [`m_db`][ldtc.lmeas.metrics.m_db].
4. Append every event to an append-only, hash-chained audit log
   ([`AuditLog`][ldtc.guardrails.audit.AuditLog]).
5. Sign and write derived indicators (NC1 bit, SC1 bit, `Mq`,
   counter) via
   [`IndicatorExporter`][ldtc.attest.exporter.IndicatorExporter].
6. Build a paper-style timeline, an SC1 table, and a manifest via
   [`reporting.artifacts.bundle`][ldtc.reporting.artifacts.bundle].

Then exercise the `Ω` battery:

```bash
ldtc omega-power-sag --config configs/profile_r0.yml --drop 0.3 --duration 10
```

The command applies a labeled power sag, freezes the C/Ex partition
during the perturbation, and writes a fresh signed indicator with the
SC1 bit decided.

Walk through the full setup in [Getting started](getting-started.md),
or skip ahead to the [Examples](examples/minimal.md).

## Why LDTC

- **Operational, not metaphysical.** NC1 and SC1 are concrete
  inequalities on `M (dB)`, `δ`, and `τ_rec`. There is nothing to
  argue about in the result; either the indicators pass or they
  don't.
- **Quietly tuning the result is hard on purpose.** `Δt` changes
  are rate-limited and audited
  ([`DeltaTGuard`][ldtc.guardrails.dt_guard.DeltaTGuard]); CI
  inflation, partition flapping during `Ω`, exogenous subsidy, and
  audit-chain breaks each invalidate a run via
  [`smelltests`][ldtc.guardrails.smelltests].
- **No raw `𝓛` ever leaves the box.** The
  [`LREG`][ldtc.guardrails.lreg.LREG] is a write-only enclave;
  exporters and CSV writers refuse rows that contain raw fields.
  Only the device-signed
  [`Indicator`][ldtc.attest.indicators] payload escapes.
- **Substrate-agnostic.** Both
  [`PlantAdapter`][ldtc.plant.adapter.PlantAdapter] (in-process
  software model) and
  [`HardwarePlantAdapter`][ldtc.plant.hw_adapter.HardwarePlantAdapter]
  (UDP / serial) satisfy the same minimal interface, so the same
  `Ω` modules work against simulation and real hardware.
- **Reproducible artifacts.** Every produced file is `chmod`-ed
  read-only on POSIX-like systems, and every figure carries a footer
  with the profile (`R0` / `R*`) and the audit hash head.

## Documentation map

- **Get started:** install the package, run R0, and read the first
  artifact bundle in [Getting started](getting-started.md).
- **Concepts:** start with the [mental
  model](concepts/mental-model.md), then read
  [definitions](concepts/definitions.md),
  [architecture](concepts/architecture.md),
  [indicators](concepts/indicators.md),
  [guardrails](concepts/guardrails.md), and the
  [paper-to-code crosswalk](concepts/paper-to-code.md).
- **Guides:** task-oriented recipes for [the multi-seed study and
  results](guides/study.md), [running the harness](guides/runs.md),
  [calibrating an R\* profile](guides/calibration.md),
  [reporting](guides/reporting.md), [hardware in the
  loop](guides/hardware.md), and [deployment](guides/deployment.md).
- **Examples:** the [minimal example](examples/minimal.md) and
  [Jupyter notebooks](examples/notebooks.md).
- **API reference:** auto-generated, one page per subpackage. Start
  with [`ldtc`](api/ldtc.md) for the package overview.
- **Meta:** [contributing](meta/contributing.md), [documentation
  style guide](meta/style-guide.md), [FAQ](meta/faq.md),
  [troubleshooting](meta/troubleshooting.md), and
  [citation](meta/citation.md).

## Next steps

- New here? Read [Getting started](getting-started.md) and then
  [Mental model](concepts/mental-model.md).
- Coming from the paper? Jump straight to the [paper-to-code
  crosswalk](concepts/paper-to-code.md).
- Deploying on real hardware? See [Hardware in the
  loop](guides/hardware.md) and
  [`HardwarePlantAdapter`][ldtc.plant.hw_adapter.HardwarePlantAdapter].
- Looking for an API symbol? Use the search box at the top of the
  page or browse the [`ldtc` API reference](api/ldtc.md).
