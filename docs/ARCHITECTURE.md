# Architecture

This repo is organized around the measurement & attestation path:

- **runtime/** — Δt scheduler + sliding windows
- **plant/** — software plant (E/T/R + exchange), swappable later for hardware via a `PlantAdapter`
- **lmeas/** — “L” measurement (two estimators), partitioning, and metrics
- **guardrails/** — enclave-like LREG, hash-chained audit, smell-tests
- **arbiter/** — refusal semantics + homeostasis controller
- **omega/** — perturbations (Ω)
- **attest/** — device-signed indicators + exporter
- **reporting/** — plots/tables for the paper

## Data Flow (per tick)

1. `scheduler` ticks at fixed Δt.
2. Controller reads state from `plant.adapter`, predicts risk, computes action, writes actuators.
3. Window buffer ingests current state.
4. When window is full, `lmeas.estimators` computes `L_loop`, `L_ex` → `M(dB)`.
5. Smell tests applied; raw values go to **LREG** (write-only).
6. Audit events appended (window measured, exports).
7. `attest.exporter` periodically emits device-signed indicators (NC1 bit, SC1 bit, Mq, counter).
8. `reporting` uses the audit + indicators to render figures/tables.

All raw `L` stays inside the process-local LREG boundary — exported data are **derived indicators** only.

## Paper crosswalk

- `lmeas/estimators.py`, `lmeas/metrics.py`: Definitions of 𝓛, dual estimators (VAR‑Granger-like linear + MI). MI paths include a sklearn MI and a Kraskov k‑NN MI (KSG) implementation with configurable k∈[3..7]. Optional TE/DI plugin hooks are provided with graceful fallbacks. M in dB, NC1/SC1 evaluation → paper §4.1 (estimators, sampling window), §4.2–§4.3 (NC1/SC1).
- `lmeas/diagnostics.py`: Per‑window stationarity checks (ADF/KPSS) and a VAR N/T ratio diagnostic; CLI logs these diagnostics to the audit for reviewer visibility.
- `lmeas/partition.py`: Deterministic C/Ex partitioning, hysteresis/anti‑flap and freeze during Ω → paper §4.1 (Deterministic C/Ex partitioning), §4.6 Box 1a (partition stability).
- `runtime/scheduler.py`, `runtime/windows.py`, `guardrails/dt_guard.py`: Δt enforcement, sliding windows, privileged Δt changes with audit → paper §4.1 (Δt constraints), §4.5 (Measurement & Attestation Guardrails: Δt governance & audit).
- `guardrails/lreg.py`, `guardrails/audit.py`, `guardrails/smelltests.py`: Enclave‑like LREG, hash‑chained audit, smell‑tests/invalidations → paper §4.5 and Box 1a (invalidations).
- `arbiter/refusal.py`: Threat model, survival‑bit/NMI refusal path, Trefuse measurement → paper §6.2.1 (Threat Model & Refusal Path); §7.6 Signature A (Command Refusal).
- `omega/power_sag.py`, `omega/ingress_flood.py`, `omega/command_conflict.py`: Ω perturbation battery (power sag, ingress flood, command conflict) → paper §4.3/§6.5 (Verification pipeline) and §7.6 (signatures table).
- `attest/indicators.py`, `attest/exporter.py`, `attest/keys.py`: Device‑signed derived indicators (NC1 bit, SC1 bit, Mq), keying → paper §4.5 (exported indicators; no raw L outside enclave) and Appendix A.
- `reporting/timeline.py`, `reporting/tables.py`: Figure‑style timelines of 𝓛loop/𝓛exchange/M with Ω shading and audit ticks; summary tables → paper Figure 1 style and §6.5 (verification outputs).
- `cli/main.py`: Orchestrates baseline → Ω battery → attestation/export; mirrors Box 2 (Engineer’s Recipe) and Phase‑III Verify flow.
- LREG/Δt/audit → paper §4.5 and Box 1a (invalidations).
- NC1/SC1 evaluator & indicators → paper §4.2–§4.3; Phase‑III Verify (Engineer’s Recipe).
