"""Command-line interface for LDTC.

This package exposes the `ldtc` console-script entry point that
wraps a fixed-Δt verification run and the `Ω` perturbation demos. The
entry function lives in [`main`][ldtc.cli.main.main]; the supporting
helpers and per-`Ω` orchestrators are in
[`cli.main`][ldtc.cli.main].

| Subcommand | Purpose |
| ---------- | ------- |
| `ldtc run` | Baseline NC1 loop. |
| `ldtc omega-power-sag` | Apply a power-sag `Ω` and evaluate SC1. |
| `ldtc omega-ingress-flood` | Burst external demand and evaluate SC1. |
| `ldtc omega-command-conflict` | Issue a risky command; measure refusal / `T_refuse`. |
| `ldtc omega-exogenous-subsidy` | Inject SoC without harvest (negative control). |
"""
