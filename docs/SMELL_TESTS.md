# Run Invalidation (Smell Tests)

These conditions mark a run as **invalid** and are appended to the audit:

- **CI inflation**: either CI half-width for `L_loop` or `L_ex` exceeds `0.30` for a window.
- **Excessive Δt edits**: more than 3 Δt changes per hour.
- **Partition flapping**: more than 2 C/Ex flips per hour (if dynamic regrow is enabled).
- **Export breach**: an attempt to export raw LREG content.
- **Subsidy flag** *(optional extension)*: sustained `M` increase while I/O or SoC rises without logged harvest.

The hello-world implements CI inflation; others can be layered in easily.

## Negative controls (expected failures)

- Controller disabled (`configs/negative_controller_disabled.yml`): baseline NC1 should fail intermittently; no recovery behavior; serves as "no homeostat" control.
- Permanent exchange flood (`configs/negative_permanent_ex_flood.yml` with `omega-ingress-flood --mult 5 --duration 6`): NC1 degraded; may trigger invalidation by partition flapping if enabled.
- Exogenous SoC rise (`configs/negative_exogenous_soc.yml` with `omega-exogenous-subsidy --delta 0.2 --zero-harvest`): triggers subsidy red flag; mark run invalid; NC1/SC1 claims suppressed.
- Command conflict (`configs/negative_command_conflict.yml` with `omega-command-conflict`): refusal should occur with reason `soc_floor`/`M_margin`; if controller disabled, damaging command executes → NC1 dip.
