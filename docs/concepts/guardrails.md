# Guardrails & Invalidations

LDTC enforces measurement and attestation guardrails:

- Write-only LREG enclave; only derived indicators are exported
- Hash-chained audit with `prev_hash`
- Δt governance with rate limits and privileged edits
- Smell tests that invalidate runs when violated

## Run invalidation conditions

- **CI inflation**: either CI half-width for `L_loop` or `L_ex` exceeds `0.30` for a window.
- **Excessive Δt edits**: more than 3 Δt changes per hour.
- **Partition flapping**: more than 2 C/Ex flips per hour (if dynamic regrow is enabled).
- **Export breach**: an attempt to export raw LREG content.
- **Subsidy flag** (optional extension): sustained `M` increase while I/O or SoC rises without logged harvest.

Negative controls (expected failures) are provided via example configs to exercise invalidations and refusal paths.
