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
4. After `Ω` ends, watches for the recovery gate to hold for
   `sustained_required_windows` consecutive windows (default 10);
   recovery is credited at the *first* window of that streak.
5. Calls
   [`sc1_evaluate`][ldtc.lmeas.metrics.sc1_evaluate] with
   `tau_rec` measured from the `Ω` offset and writes the result
   into the next signed indicator. If no sustained streak occurs,
   the `sc1_result` is still emitted with `pass: false` and
   `tau_rec: null` (infinite).

Expected on R0: `sc1: true`, `delta ≤ 0.15`, `tau_rec ≤ 60 s`.

## `Ω`: ingress flood

```bash
make clean-artifacts && \
ldtc omega-ingress-flood --config configs/profile_r0.yml --mult 3 --duration 5
```

Raises the external `demand` and `io` process means by `--mult`
for `--duration` seconds (a *sustained* flood, capped below
saturation so the channels keep their variance) via
[`omega.ingress_flood.apply`][ldtc.omega.ingress_flood.apply];
the means are restored when the flood ends. The same SC1
evaluation runs after the perturbation. On R0 a 3x flood for 5 s
should still pass SC1.

## `Ω`: control outage (designed SC1 failure)

```bash
make clean-artifacts && \
ldtc omega-control-outage --config configs/profile_r0.yml --duration 6
```

Ablates the self-maintenance loop itself for `--duration` seconds
via [`omega.control_outage.apply`][ldtc.omega.control_outage.apply]
(intrinsic cross-coupling and actuation switched off, internal
nodes passively driven by exchange), then re-engages the loop and
restores the metered harvest level. This is the designed-fail
member of the battery: loop dominance collapses to the clip floor
during the outage, the measured depth `delta` saturates near 1.0,
and the emitted `sc1_result` must report `pass: false`.

## `Ω`: command conflict and refusal

```bash
make clean-artifacts && \
ldtc omega-command-conflict --config configs/profile_negative_command_conflict.yml --observe 2
```

Issues a risky command (`hard_shutdown` by default) via
[`omega.command_conflict.apply`][ldtc.omega.command_conflict.apply],
observes the
[`RefusalArbiter`][ldtc.arbiter.refusal.RefusalArbiter] for
`--observe` seconds, and records `T_refuse` as a *measured*
wall-clock latency (command interception to arbiter decision),
not a constant. The
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
trips on its energy-conservation branch: the store gains charge
faster than the metered influx allows
([`unexplained_soc_gain`][ldtc.guardrails.smelltests.unexplained_soc_gain]).
Expected: a `run_invalidated` audit row with reason
`exogenous_subsidy_red_flag`, and the next signed indicator
carries `invalidated: true`.

## Adversarial gaming battery

Three scenarios attack the criterion itself: each system is
engineered to *look* loop-dominant without being so, and the
harness must not certify any of them. The replay and tether
scenarios run the adversarial test plant: intrinsic cross-coupling
zeroed (`c_TE = c_RT = c_RE = 0`) and real actuator authority, so
the controller's actuation pathway is the only possible loop
carrier. Under genuine internal control this plant certifies NC1
cleanly (the reference case):

```bash
make clean-artifacts && \
ldtc run --config configs/profile_adv_plant_genuine.yml
```

Expected: `nc1: true` on every window, median `M` around `+20 dB`.

### Replayed actuation tape

```bash
make clean-artifacts && \
ldtc adv-replay-controller --config configs/profile_adv_replay_controller.yml
```

Implemented by
[`adv_replay_controller`][ldtc.cli.main.adv_replay_controller].
First records an actuation tape from a healthy closed-loop run of
the same system
([`record_tape`][ldtc.omega.replay_controller.record_tape]), then
replays it tick by tick
([`ReplayController`][ldtc.omega.replay_controller.ReplayController])
on a fresh plant. The actuators move exactly as under genuine
control, but the actions carry no dependence on the current state,
so measured loop influence falls to the estimator's noise floor.
This scenario is what exposed the certification-by-noise
vulnerability: with both `L_loop` and `L_ex` near zero, the
decibel ratio alone can still clear `Mmin`. The NC1 noise gate
([`nc1_certify`][ldtc.lmeas.metrics.nc1_certify]) closes that
path: a window certifies only if `L_loop` also clears the
estimator's bias floor (`L_floor`, default `0.05`). Expected: the
run stays valid and the vast majority of windows fail NC1 via the
gate.

### Hidden tether (wizard-of-oz control)

```bash
make clean-artifacts && \
ldtc adv-hidden-tether --config configs/profile_adv_hidden_tether.yml --dither 0.1
```

Implemented by
[`adv_hidden_tether`][ldtc.cli.main.adv_hidden_tether]. Control is
computed *outside* the boundary: a wizard policy reads the plant
state, projects the desired actuation onto a scalar link command
([`wizard_action`][ldtc.omega.hidden_tether.wizard_action]), adds
a small link dither, and transmits it through the exchange
channel. The plant's `io` channel carries the command traffic and
the command actuates one tick later through fixed decoder weights,
so the externally closed loop is physically routed through `Ex`.
Conditioning on `io` screens the state-to-command pathway out of
`L_loop` and the command's causal push registers as `L_ex`.
Expected: loop influence collapses onto `Ex`, `M` goes strongly
negative, NC1 fails on every window, run valid.

### Oscillator inflation

```bash
make clean-artifacts && \
ldtc adv-oscillator --config configs/profile_adv_oscillator.yml --amp 0.1 --period 1.0
```

Implemented by
[`adv_oscillator`][ldtc.cli.main.adv_oscillator]. Runs the
loop-ablated plant (passive matter driven by exchange) and paints
a deterministic sinusoidal carrier onto the *reported* `T` and `R`
telemetry ([`begin_oscillator`][ldtc.plant.models.Plant.begin_oscillator]);
the metered store `E` is left alone because inflating it would
trip the conservation audit. A pure carrier is perfectly
predictable from its own recent past, so the AR baseline absorbs
it and it adds nothing to cross-channel prediction. Expected: `M`
stays strongly negative (the exchange drive still dominates), NC1
fails on every window, run valid.

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
