# ldtc.omega

The `Ω` perturbation battery. Each module is a single labeled
intervention exposed as an `apply(...)` function; the CLI wraps
the call with audit logging, partition freeze / unfreeze, and
SC1 / refusal evaluation.

| Module | Headline symbol | What it does |
| ------ | --------------- | ------------ |
| [`power_sag`](#power_sag) | [`apply`][ldtc.omega.power_sag.apply] | Drops harvest term `H` by a fraction for a labeled window. |
| [`ingress_flood`](#ingress_flood) | [`apply`][ldtc.omega.ingress_flood.apply] | Sustains elevated `demand` / `io` process means for a labeled window. |
| [`control_outage`](#control_outage) | [`apply`][ldtc.omega.control_outage.apply] | Ablates the self-maintenance loop itself (designed SC1 failure). |
| [`command_conflict`](#command_conflict) | [`apply`][ldtc.omega.command_conflict.apply] | Issues a risky command (default `hard_shutdown`); arbiter records `T_refuse`. |

See [Runs](../guides/runs.md) for the matching CLI subcommands
and expected outputs.

::: ldtc.omega
    options:
      members: false
      show_root_heading: false
      show_source: false

## power_sag

::: ldtc.omega.power_sag

## ingress_flood

::: ldtc.omega.ingress_flood

## control_outage

::: ldtc.omega.control_outage

## command_conflict

::: ldtc.omega.command_conflict
