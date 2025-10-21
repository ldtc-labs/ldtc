# LDTC

LDTC is a single-machine, real-time verification harness for loop-dominance (NC1) and resilience (SC1) used in the accompanying manuscript. It measures closed-loop dominance M(dB), applies guardrails, runs Ω perturbations, and exports device-signed derived indicators only.

- **Deterministic measurement**: fixed Δt scheduler, sliding windows, C/Ex partition, dual estimators
- **Guardrails**: LREG enclave, hash-chained audit, smell tests/invalidations, Δt governance
- **Attestation**: derived indicators (NC1, SC1, Mq, counters) signed and export-only
- **Ω battery**: power sag, ingress flood, command conflict; refusal semantics
- **Reporting**: timeline plots and SC1 tables for paper-quality artifacts

Use the sidebar to browse Concepts, Guides, API reference, and Examples.
