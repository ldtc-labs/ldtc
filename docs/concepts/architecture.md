# Architecture

The repository is organized around the measurement and attestation
path. Each subpackage has a single, narrow job, and the boundaries
between them are deliberately strict (in particular: nothing
upstream of [`ldtc.attest`][ldtc.attest] is allowed to read raw
`𝓛` out of [`ldtc.guardrails.lreg`][ldtc.guardrails.lreg]).

## Module map

| Subpackage | Job | Headline symbols |
| ---------- | --- | ---------------- |
| [`runtime`][ldtc.runtime] | Fixed-`Δt` scheduler and sliding-window buffer. | [`FixedScheduler`][ldtc.runtime.scheduler.FixedScheduler], [`SlidingWindow`][ldtc.runtime.windows.SlidingWindow] |
| [`plant`][ldtc.plant] | Software plant `(E, T, R, demand, io, H)` plus a UDP / serial hardware adapter. | [`Plant`][ldtc.plant.models.Plant], [`PlantAdapter`][ldtc.plant.adapter.PlantAdapter], [`HardwarePlantAdapter`][ldtc.plant.hw_adapter.HardwarePlantAdapter] |
| [`lmeas`][ldtc.lmeas] | "L" measurement: estimators, partitioning, diagnostics, metrics. | [`estimate_L`][ldtc.lmeas.estimators.estimate_L], [`PartitionManager`][ldtc.lmeas.partition.PartitionManager], [`greedy_suggest_C`][ldtc.lmeas.partition.greedy_suggest_C], [`m_db`][ldtc.lmeas.metrics.m_db], [`sc1_evaluate`][ldtc.lmeas.metrics.sc1_evaluate] |
| [`guardrails`][ldtc.guardrails] | Enclave-like LREG, hash-chained audit, smell tests, `Δt` governance. | [`LREG`][ldtc.guardrails.lreg.LREG], [`AuditLog`][ldtc.guardrails.audit.AuditLog], [`DeltaTGuard`][ldtc.guardrails.dt_guard.DeltaTGuard], [`smelltests`][ldtc.guardrails.smelltests] |
| [`arbiter`][ldtc.arbiter] | Refusal semantics and the homeostasis controller policy. | [`RefusalArbiter`][ldtc.arbiter.refusal.RefusalArbiter], [`ControllerPolicy`][ldtc.arbiter.policy.ControllerPolicy] |
| [`omega`][ldtc.omega] | Labeled `Ω` perturbations. | [`omega.power_sag`][ldtc.omega.power_sag], [`omega.ingress_flood`][ldtc.omega.ingress_flood], [`omega.command_conflict`][ldtc.omega.command_conflict] |
| [`attest`][ldtc.attest] | Device-signed indicators and exporter. | [`build_and_sign`][ldtc.attest.indicators.build_and_sign], [`IndicatorExporter`][ldtc.attest.exporter.IndicatorExporter] |
| [`reporting`][ldtc.reporting] | Paper-quality timeline plots, SC1 tables, and verification bundle. | [`render_paper_timeline`][ldtc.reporting.timeline.render_paper_timeline], [`write_sc1_table`][ldtc.reporting.tables.write_sc1_table], [`bundle`][ldtc.reporting.artifacts.bundle] |
| [`cli`][ldtc.cli] | Glue: subcommands `run`, `omega-power-sag`, etc. | [`run_baseline`][ldtc.cli.main.run_baseline], [`omega_power_sag`][ldtc.cli.main.omega_power_sag] |

## Data flow per tick

```text
                ┌──────────────────────────────────────────────────────┐
                │                  FixedScheduler  (Δt)                │
                └──────────────────────────────────────────────────────┘
                                          │
                                          ▼
            ┌─────────────────┐    state    ┌────────────────────┐
            │  PlantAdapter   │────────────▶│  ControllerPolicy  │
            │  (sw / hw)      │◀────────────│     + Refusal      │
            └─────────────────┘   action    └────────────────────┘
                     │
                     │ state'
                     ▼
            ┌─────────────────┐
            │  SlidingWindow  │
            └─────────────────┘
                     │ when full
                     ▼
            ┌─────────────────┐
            │   estimate_L    │──── LResult, CIs ──┐
            │ + diagnostics   │                    │
            └─────────────────┘                    │
                     │                             │
                     ▼                             ▼
            ┌─────────────────┐         ┌──────────────────┐
            │  PartitionMgr   │         │   smell tests    │
            │  greedy_regrow  │         │  ci_inflation,   │
            └─────────────────┘         │  partition flap, │
                     │                  │  Δt edits, etc.  │
                     │                  └──────────────────┘
                     │                              │
                     ▼                              ▼
            ┌──────────────────────────────────────────────┐
            │   LREG (write-only)   +   AuditLog (chain)   │
            └──────────────────────────────────────────────┘
                                          │
                                          ▼
                          ┌─────────────────────────────┐
                          │  IndicatorExporter (CBOR)   │
                          │   build_and_sign  (Ed25519) │
                          └─────────────────────────────┘
                                          │
                                          ▼
                          ┌─────────────────────────────┐
                          │   reporting.artifacts       │
                          │   timeline / table / mfst   │
                          └─────────────────────────────┘
```

The arrow from `LREG` to the exporter is intentionally narrow:
only [`LREG.derive`][ldtc.guardrails.lreg.LREG.derive] crosses
that boundary, and what it returns is what
[`build_and_sign`][ldtc.attest.indicators.build_and_sign] turns
into a CBOR payload. Raw `𝓛` never leaves.

## Per-tick sequence

1. `scheduler` ticks at fixed `Δt`.
2. Controller reads state from `plant.adapter`, predicts risk via
   `LREG.latest()`, computes an action, writes actuators.
3. The window buffer ingests the next state vector.
4. When the window is full,
   [`estimate_L`][ldtc.lmeas.estimators.estimate_L] computes
   `(𝓛_loop, 𝓛_ex)` with bootstrapped CIs and
   [`m_db`][ldtc.lmeas.metrics.m_db] turns them into `M (dB)`.
5. Smell tests run; raw `𝓛` is appended to `LREG` (write-only).
6. Audit events are appended (`window_measured`, optionally
   `window_diagnostics`, `partition_flip`, etc.).
7. Periodically (rate-limited),
   [`IndicatorExporter`][ldtc.attest.exporter.IndicatorExporter]
   emits a device-signed payload (`nc1`, `sc1`, `mq`, `counter`,
   `profile_id`, `audit_prev_hash`, `invalidated`).
8. `reporting` reads the audit log to render figures, tables, and
   the manifest.

All raw `𝓛` stays inside the process-local `LREG` boundary;
exported data is **derived indicators only**.

## Paper crosswalk

The full per-section mapping lives in
[paper-to-code](paper-to-code.md). A condensed summary:

- [`lmeas/estimators.py`][ldtc.lmeas.estimators] and
  [`lmeas/metrics.py`][ldtc.lmeas.metrics]: definitions of `𝓛`,
  the dual estimators (linear / VAR-Granger-like and Kraskov k-NN
  MI), and `M (dB)`. NC1 / SC1 evaluation maps to the paper's
  "Formal Criterion" (estimators, sampling window; NC1; SC1).
- [`lmeas/diagnostics.py`][ldtc.lmeas.diagnostics]: per-window
  stationarity (ADF / KPSS) and VAR `N / T` ratio diagnostics
  surfaced into the audit.
- [`lmeas/partition.py`][ldtc.lmeas.partition]: deterministic
  C/Ex partitioning, hysteresis, anti-flap, and the freeze during
  `Ω` per the "Formal Criterion" (deterministic C/Ex
  partitioning) and the "Smell-tests & run-invalidation rules".
- [`runtime/scheduler.py`][ldtc.runtime.scheduler],
  [`runtime/windows.py`][ldtc.runtime.windows], and
  [`guardrails/dt_guard.py`][ldtc.guardrails.dt_guard]: `Δt`
  enforcement and audited privileged edits per the "Formal
  Criterion" and "Measurement & Attestation Guardrails".
- [`guardrails/lreg.py`][ldtc.guardrails.lreg],
  [`guardrails/audit.py`][ldtc.guardrails.audit], and
  [`guardrails/smelltests.py`][ldtc.guardrails.smelltests]: the
  enclave-like LREG, hash-chained audit, and the smell-test
  battery per the "Measurement & Attestation Guardrails" and the
  Smell-tests box.
- [`arbiter/refusal.py`][ldtc.arbiter.refusal]: the threat model,
  survival-bit / NMI refusal path, and `T_refuse` measurement per
  the "Blueprint" (Threat Model & Refusal Path) and the "Predicted
  Observable Signatures".
- [`omega/power_sag.py`][ldtc.omega.power_sag],
  [`omega/ingress_flood.py`][ldtc.omega.ingress_flood], and
  [`omega/command_conflict.py`][ldtc.omega.command_conflict]: the
  `Ω` battery per the "Formal Criterion" (SC1), the "Simulation
  Study" battery, and the "Predicted Observable Signatures".
- [`attest/indicators.py`][ldtc.attest.indicators],
  [`attest/exporter.py`][ldtc.attest.exporter], and
  [`attest/keys.py`][ldtc.attest.keys]: device-signed derived
  indicators (NC1 bit, SC1 bit, `Mq`) and keying per the
  "Measurement & Attestation Guardrails" and Appendix A.
- [`reporting/timeline.py`][ldtc.reporting.timeline] and
  [`reporting/tables.py`][ldtc.reporting.tables]: figure-style
  timelines and summary tables per the paper figures and the
  "Blueprint" (Verification Pipeline).
- [`cli/main.py`][ldtc.cli.main]: orchestrates baseline → `Ω`
  battery → attestation / export per the Training & Verification
  Protocol box (Engineer's Recipe) and the Phase III verify flow.

## Next steps

- [Lifecycle](lifecycle.md): the same picture, but in time order
  for one CLI invocation.
- [Mental model](mental-model.md): the one-paragraph story of
  what NC1 / SC1 measure and how the harness keeps them honest.
- [Indicators](indicators.md): exactly what leaves the box.
- [Guardrails](guardrails.md): how invalidation works.
