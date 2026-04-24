"""Guardrails and governance for LDTC runs.

Components in this subpackage protect the integrity of an LDTC run by
limiting how the harness can be reconfigured at runtime, what can leave
the measurement enclave, and which conditions silently invalidate a
result:

- [`audit`][ldtc.guardrails.audit] is the append-only, hash-chained
  JSONL audit log.
- [`dt_guard`][ldtc.guardrails.dt_guard] provides privileged `Δt`
  governance with rate limits and audit.
- [`lreg`][ldtc.guardrails.lreg] is the enclave-like register for raw
  `𝓛` and CIs; only derived indicators are exported.
- [`smelltests`][ldtc.guardrails.smelltests] runs measurement-fragility
  and anti-gaming checks (CI inflation, partition flips, jitter,
  exogenous subsidy, audit-chain integrity).

Together these enforce LDTC's "no quietly-tuned NC1/SC1 result" rule:
any change to `Δt`, any partition flip during `Ω`, any CI blow-up, or
any leakage of raw `𝓛` either gets rejected or records a
`run_invalidated` event in the audit log.
"""
