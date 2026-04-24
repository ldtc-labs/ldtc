# Guardrails and invalidations

LDTC's job is not only to *measure* NC1 / SC1 but to make it hard
to quietly tune the result. The
[`ldtc.guardrails`][ldtc.guardrails] package is where that
happens. There are four moving parts:

| Piece | Code | Purpose |
| ----- | ---- | ------- |
| LREG enclave | [`LREG`][ldtc.guardrails.lreg.LREG] | Write-only registry for raw `𝓛`. |
| Audit log | [`AuditLog`][ldtc.guardrails.audit.AuditLog] | Append-only, hash-chained event journal. |
| `Δt` governance | [`DeltaTGuard`][ldtc.guardrails.dt_guard.DeltaTGuard] | Rate-limits and audits `Δt` changes. |
| Smell tests | [`smelltests`][ldtc.guardrails.smelltests] | Per-window invalidation heuristics. |

## What gets watched

Defaults below come from
[`SmellConfig`][ldtc.guardrails.smelltests.SmellConfig]. They are
all overridable per profile.

| Smell test | Threshold | Code | What it catches |
| ---------- | --------- | ---- | --------------- |
| **CI half-width** | `> 0.30` on `𝓛_loop` or `𝓛_ex` | [`invalid_by_ci`][ldtc.guardrails.smelltests.invalid_by_ci] | One bad window with a blown-up CI. |
| **CI inflation vs baseline** | median half-width `> 2 ×` baseline median over `5` windows | [`invalid_by_ci_history`][ldtc.guardrails.smelltests.invalid_by_ci_history] | Slow-creeping noise, bad seed of the bootstrap, etc. |
| **Excessive `Δt` edits** | `> 3` per rolling hour | enforced inline by [`DeltaTGuard`][ldtc.guardrails.dt_guard.DeltaTGuard] | Operator nudging `Δt` to make `M` look better. |
| **Partition flapping** | `> 2` flips per hour | [`invalid_by_partition_flips`][ldtc.guardrails.smelltests.invalid_by_partition_flips] | A regrowth knob that chatters. |
| **Flip during `Ω`** | any | [`invalid_flip_during_omega`][ldtc.guardrails.smelltests.invalid_flip_during_omega] | A reshuffle that happens to make SC1 pass. |
| **`Δt` jitter excess** | `p95(|jitter|) / Δt > 0.25` | computed by [`SchedulerStats`][ldtc.runtime.scheduler.TickStats] | The scheduler did not actually hold `Δt`. |
| **Audit chain broken** | any `prev_hash` mismatch | [`audit_chain_broken`][ldtc.guardrails.smelltests.audit_chain_broken] | Torn write, edited audit, etc. |
| **Raw LREG breach** | any audit row with raw `𝓛` fields | [`audit_contains_raw_lreg_values`][ldtc.guardrails.smelltests.audit_contains_raw_lreg_values] | Something tried to log raw measurements. |
| **Exogenous subsidy** | `M` rising while I/O suspicious or SoC rising without harvest | [`exogenous_subsidy_red_flag`][ldtc.guardrails.smelltests.exogenous_subsidy_red_flag] | Hidden energy source masquerading as loop dominance. |

When any guard returns `True` the CLI:

1. Calls
   [`LREG.invalidate(reason)`][ldtc.guardrails.lreg.LREG.invalidate]
   so subsequent indicators carry `invalidated = true`.
2. Appends a `run_invalidated` audit record with the reason and
   any quantitative payload.

Indicators after that point still get signed, but their
`invalidated` bit is `true`, and downstream verifiers should treat
the whole run as failed.

## Multi-run audit files

Each CLI invocation starts a fresh audit chain (counter resets,
`prev_hash = GENESIS`) but, by default, *appends* to the same
`artifacts/audits/audit.jsonl`. The post-run integrity check
validates the entire file, so after the first run, subsequent runs
in the same file will trip an "Audit chain broken" invalidation.
For clean, non-invalidated runs, clear artifacts between commands:

```bash
make clean-artifacts && ldtc run --config configs/profile_r0.yml
make clean-artifacts && ldtc omega-power-sag --config configs/profile_r0.yml --drop 0.35 --duration 8
```

If you are iterating on figures or manifests, this invalidation is
expected and does not prevent artifacts from being produced; it
only reflects multiple runs aggregated into one audit file.

## Negative controls

Several configs in `configs/` are *intended* to fail, so you can
confirm the guards work end-to-end:

| Config | What it triggers |
| ------ | ---------------- |
| `profile_negative_command_conflict.yml` | `omega-command-conflict` exercises `RefusalArbiter`; `T_refuse` should be measured and a `refusal_event` should appear in the audit. |
| `profile_negative_controller_disabled.yml` | Disables the controller; NC1 should fail (no loop). |
| `profile_negative_exogenous_soc.yml` | `omega-exogenous-subsidy` should trip the exogenous-subsidy smell test. |
| `profile_negative_permanent_ex_flood.yml` | `omega-ingress-flood` with no recovery; SC1 should fail. |

Run any of these with `make clean-artifacts && ldtc <subcommand>
--config configs/<negative.yml>`, then read the
`run_invalidated` records in `artifacts/audits/audit.jsonl`.

## What guarded actually means

The guarantees the harness gives you:

- **No raw `𝓛` ever appears in a CSV, indicator, or audit row.**
  Both the exporter and the CSV writer call
  [`audit_contains_raw_lreg_values`][ldtc.guardrails.smelltests.audit_contains_raw_lreg_values]
  before emitting; LREG itself only exposes
  [`derive`][ldtc.guardrails.lreg.LREG.derive] and
  [`latest`][ldtc.guardrails.lreg.LREG.latest].
- **Every `Δt` change is rate-limited and audited.** A change has
  to go through
  [`DeltaTGuard.change_dt`][ldtc.guardrails.dt_guard.DeltaTGuard.change_dt],
  which appends a `dt_changed` record on success or refuses on
  rate-limit failure (see
  [`can_change`][ldtc.guardrails.dt_guard.DeltaTGuard.can_change]).
- **The audit chain is verified twice:** once in process and once
  by re-reading the file from disk. A torn write or a partial
  flush still gets caught.
- **Indicators and audit cannot disagree.** A signed indicator's
  `invalidated` bit comes from the same in-process flag that
  appended the most recent `run_invalidated` audit row.

## See also

- [Lifecycle](lifecycle.md): when each guard runs during a CLI
  invocation.
- [Definitions](definitions.md): formal statements of `Δt`,
  `𝓛`, `M`, partition.
- [`ldtc.guardrails`][ldtc.guardrails]: API reference for every
  guard and the `SmellConfig` thresholds.
