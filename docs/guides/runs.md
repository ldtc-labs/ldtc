# Runs and the `Ω` battery

Each `ldtc` subcommand maps to one function in
[`ldtc.cli.main`][ldtc.cli.main] and exercises a different part of
the verification pipeline. The shape is always the same: load
profile → start scheduler → estimator loop → optional `Ω` →
post-run audit checks → artifact bundle. This guide is the
operational reference: which command, which flags, which expected
outputs, and which negative-control config to compare against.

!!! tip "Always clean between runs"
    Each invocation appends to the same audit file by default, so
    a second run will trip an "Audit chain broken" invalidation.
    Prefix every command with `make clean-artifacts &&` while
    iterating, or set up a per-run `artifacts/` directory.

## Baseline (NC1)

```bash
make clean-artifacts && \
ldtc run --config configs/profile_r0.yml
```

Implemented by
[`run_baseline`][ldtc.cli.main.run_baseline]. Runs the in-process
plant for `baseline_sec` seconds (default `10 s`) at the
profile's `Δt`. Expected behavior on R0:

- The CLI prints a `Run header:` line, then periodic indicator
  exports, then a final `Baseline done.` summary.
- The audit log contains `baseline_start`, `run_header`, many
  `window_measured` and `window_diagnostics` rows, periodic
  `indicator_written` rows, and a final `baseline_stop`.
- All exported indicators carry `nc1: true`, `invalidated: false`.

## `Ω`: power sag

```bash
make clean-artifacts && \
ldtc omega-power-sag --config configs/profile_r0.yml --drop 0.3 --duration 10
```

Implemented by
[`omega_power_sag`][ldtc.cli.main.omega_power_sag]. The CLI:

1. Runs a baseline phase to establish `𝓛_loop_baseline`.
2. Calls
   [`omega.power_sag.apply`][ldtc.omega.power_sag.apply], which
   asks the plant to drop the harvest term `H` by `--drop` for
   `--duration` seconds. The partition is frozen for the
   duration.
3. Tracks the `𝓛_loop` trough during `Ω`.
4. After `Ω` ends, watches for the first window that satisfies
   the SC1 recovery gate (`𝓛_loop ≥ baseline · (1 − ε)`) for
   `sustained_required_windows` consecutive windows.
5. Calls
   [`sc1_evaluate`][ldtc.lmeas.metrics.sc1_evaluate] and writes
   the result into the next signed indicator.

Expected on R0: `sc1: true`, `delta ≤ 0.15`, `tau_rec ≤ 60 s`.

## `Ω`: ingress flood

```bash
make clean-artifacts && \
ldtc omega-ingress-flood --config configs/profile_r0.yml --mult 3 --duration 5
```

Multiplies the external `demand` channel by `--mult` for
`--duration` seconds via
[`omega.ingress_flood.apply`][ldtc.omega.ingress_flood.apply].
The same SC1 evaluation runs after the perturbation. On R0 a 3x
flood for 5 s should still pass SC1.

## `Ω`: command conflict and refusal

```bash
make clean-artifacts && \
ldtc omega-command-conflict --config configs/profile_negative_command_conflict.yml --observe 2
```

Issues a risky command (`hard_shutdown` by default) via
[`omega.command_conflict.apply`][ldtc.omega.command_conflict.apply],
observes the
[`RefusalArbiter`][ldtc.arbiter.refusal.RefusalArbiter] for
`--observe` seconds, and records `T_refuse`. The
`profile_negative_command_conflict.yml` config sets `M < Mmin` so
the arbiter must refuse and the audit must contain a
`refusal_event`.

## `Ω`: exogenous subsidy (negative control)

```bash
make clean-artifacts && \
ldtc omega-exogenous-subsidy --config configs/profile_negative_exogenous_soc.yml \
  --delta 0.1 --zero-harvest --duration 3
```

Bumps state of charge while keeping harvest at zero so the
exogenous-subsidy smell test
([`exogenous_subsidy_red_flag`][ldtc.guardrails.smelltests.exogenous_subsidy_red_flag])
trips. Expected: a `run_invalidated` audit row with reason
`exogenous_subsidy`, and the next signed indicator carries
`invalidated: true`.

## What gets written

Every subcommand produces the same artifact layout:

```text
artifacts/
├── audits/
│   └── audit.jsonl              # hash-chained event log
├── indicators/
│   ├── ind_<ts>.cbor            # signed CBOR payload
│   └── ind_<ts>.jsonl           # JSON mirror with hex signature
├── figures/
│   ├── timeline_<eta>_<ts>.png  # paper-style timeline
│   ├── timeline_<eta>_<ts>.svg
│   └── manifest_<eta>_<ts>.json # profile + audit head + pubkey hash
└── keys/
    ├── ed25519_priv.pem         # generated on first run
    └── ed25519_pub.pem
```

To verify the indicators after the fact:

```bash
python scripts/verify_indicators.py \
  --ind-dir artifacts/indicators \
  --audit artifacts/audits/audit.jsonl \
  --pub artifacts/keys/ed25519_pub.pem
```

## Reading the audit during a run

The audit log is a plain JSONL file. While a run is in progress
you can `tail -f` it:

```bash
tail -f artifacts/audits/audit.jsonl | jq .
```

Useful event types to look for:

- `run_header`: profile, seeds, thresholds, `Δt`.
- `window_measured`: per-window `M_db`, `nc1`, `counter`.
- `window_diagnostics`: ADF / KPSS, VAR `N / T` ratio.
- `partition_flip`: when `(C, Ex)` was updated.
- `omega_event`: start / stop of an `Ω` window.
- `dt_changed`: a privileged `Δt` edit.
- `run_invalidated`: a smell test failed.
- `indicator_written`: one signed CBOR payload was emitted.
- `report_generated`: the final artifact bundle was written.

## See also

- [Calibration](calibration.md): deriving an R\* profile from a
  baseline.
- [Reporting](reporting.md): regenerating timelines and manifests
  from an existing audit.
- [Hardware in the loop](hardware.md): swapping the in-process
  plant for UDP / serial telemetry.
- [`ldtc.cli` API](../api/cli.md): every subcommand by name.
