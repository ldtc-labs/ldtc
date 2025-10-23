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

### Multi-run audits (same file)

Each CLI invocation starts a fresh audit chain (counter resets; `prev_hash=GENESIS`) but, by default, appends to the same `artifacts/audits/audit.jsonl`. The post-run integrity check validates the entire file, so after the first run, subsequent runs in the same file will trip an "Audit chain broken" invalidation. For clean, non-invalidated runs, clear artifacts between commands, e.g.:

```bash
make clean-artifacts && ldtc run --config configs/profile_r0.yml
make clean-artifacts && ldtc omega-power-sag --config configs/profile_r0.yml --drop 0.35 --duration 8
```

If you are iterating on figures or manifests, this invalidation is expected and does not prevent artifacts from being produced; it only reflects multiple runs aggregated into a single audit file.

Negative controls (expected failures) are provided via example configs to exercise invalidations and refusal paths.
