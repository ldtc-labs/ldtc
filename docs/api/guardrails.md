# ldtc.guardrails

Measurement and attestation guardrails. The pieces here are what
make the harness's NC1 / SC1 results hard to silently
misconfigure.

| Module | Headline symbols | Use it for |
| ------ | ---------------- | ---------- |
| [`audit`](#audit) | [`AuditLog`][ldtc.guardrails.audit.AuditLog] | Append-only, hash-chained event journal. Every event in a run; every record carries `prev_hash = SHA256(prev_record)`. |
| [`dt_guard`](#dt_guard) | [`DeltaTGuard`][ldtc.guardrails.dt_guard.DeltaTGuard], [`DtGuardConfig`][ldtc.guardrails.dt_guard.DtGuardConfig] | Rate-limited, audited `Δt` changes. |
| [`lreg`](#lreg) | [`LREG`][ldtc.guardrails.lreg.LREG], [`LEntry`][ldtc.guardrails.lreg.LEntry] | Write-only enclave that holds raw `𝓛`. Only `derive()` and `latest()` exit. |
| [`smelltests`](#smelltests) | [`SmellConfig`][ldtc.guardrails.smelltests.SmellConfig], [`invalid_by_ci`][ldtc.guardrails.smelltests.invalid_by_ci], [`audit_chain_broken`][ldtc.guardrails.smelltests.audit_chain_broken], [`audit_contains_raw_lreg_values`][ldtc.guardrails.smelltests.audit_contains_raw_lreg_values], [`exogenous_subsidy_red_flag`][ldtc.guardrails.smelltests.exogenous_subsidy_red_flag] | Per-window invalidation heuristics and post-run integrity checks. |

::: ldtc.guardrails
    options:
      members: false
      show_root_heading: false
      show_source: false

## audit

::: ldtc.guardrails.audit

## dt_guard

::: ldtc.guardrails.dt_guard

## lreg

::: ldtc.guardrails.lreg

## smelltests

::: ldtc.guardrails.smelltests
