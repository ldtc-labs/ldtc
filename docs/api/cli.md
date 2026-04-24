# ldtc.cli

The verification harness's entry points. Exposes the `ldtc *`
subcommands on the command line, all of which live as functions
in [`ldtc.cli.main`][ldtc.cli.main].

| Subcommand | Function | What it does |
| ---------- | -------- | ------------ |
| `ldtc run` | [`run_baseline`][ldtc.cli.main.run_baseline] | Baseline NC1 verification loop. |
| `ldtc omega-power-sag` | [`omega_power_sag`][ldtc.cli.main.omega_power_sag] | Apply a power sag and evaluate SC1. |
| `ldtc omega-ingress-flood` | [`omega_ingress_flood`][ldtc.cli.main.omega_ingress_flood] | Multiply external demand and evaluate SC1. |
| `ldtc omega-command-conflict` | [`omega_command_conflict`][ldtc.cli.main.omega_command_conflict] | Issue a risky command and observe refusal. |
| `ldtc omega-exogenous-subsidy` | [`omega_exogenous_subsidy`][ldtc.cli.main.omega_exogenous_subsidy] | Inject SoC without harvest; should invalidate. |

Each handler follows the same five-stage shape (see
[Lifecycle](../concepts/lifecycle.md)):

1. Load profile and seed RNGs.
2. Build adapters, audit log, LREG, exporter, scheduler, and
   guardrails.
3. Run a baseline phase, optionally an `Ω` window, and a
   recovery phase.
4. Post-run audit checks (chain integrity, no raw LREG leakage).
5. Build a verification artifact bundle via
   [`reporting.artifacts.bundle`][ldtc.reporting.artifacts.bundle].

::: ldtc.cli
    options:
      members: false
      show_root_heading: false
      show_source: false

## main

::: ldtc.cli.main
