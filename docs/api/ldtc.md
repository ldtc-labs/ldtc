# ldtc

Top-level package overview. Use this page as the entry point for
the API reference; each subpackage has its own page in the
sidebar with a curated layout. The package docstring below is
the same one you get from `import ldtc; help(ldtc)` in a Python
shell.

::: ldtc

## Subpackages

| Subpackage | Page | One-liner |
| ---------- | ---- | --------- |
| [`ldtc.runtime`][ldtc.runtime] | [runtime](runtime.md) | Fixed-`Δt` scheduler and sliding-window buffer. |
| [`ldtc.plant`][ldtc.plant] | [plant](plant.md) | Software plant and UDP / serial hardware adapter. |
| [`ldtc.lmeas`][ldtc.lmeas] | [lmeas](lmeas.md) | "L" measurement: estimators, partition, metrics, diagnostics. |
| [`ldtc.guardrails`][ldtc.guardrails] | [guardrails](guardrails.md) | LREG enclave, audit log, `Δt` governance, smell tests. |
| [`ldtc.arbiter`][ldtc.arbiter] | [arbiter](arbiter.md) | Refusal semantics and homeostasis controller. |
| [`ldtc.omega`][ldtc.omega] | [omega](omega.md) | Labeled `Ω` perturbations. |
| [`ldtc.attest`][ldtc.attest] | [attest](attest.md) | Device-signed indicators and exporter. |
| [`ldtc.reporting`][ldtc.reporting] | [reporting](reporting.md) | Paper-style timelines, SC1 tables, and verification bundles. |
| [`ldtc.cli`][ldtc.cli] | [cli](cli.md) | The `ldtc *` subcommands. |

## See also

- [Architecture](../concepts/architecture.md): the static module
  map and data-flow diagram.
- [Lifecycle](../concepts/lifecycle.md): how the modules above
  cooperate during one CLI invocation.
- [Mental model](../concepts/mental-model.md): the one-paragraph
  story.
