# Paper → Code Matrix (Crosswalk)

A quick crosswalk from the paper (§/Box) to concrete code, commands, and produced artifacts.

| Paper §/Box | Short text | Files/Functions | Command | Artifact produced |
|---|---|---|---|---|
| §4.2 | NC1 loop‑dominance: M(dB) ≥ Mmin → nc1 bit | `lmeas/metrics.py::m_db`; `lmeas/estimators.py::estimate_L`; `cli/main.py::run_baseline` | `ldtc run --config configs/profile_r0.yml` | `artifacts/indicators/ind_*.{jsonl,cbor}`; `artifacts/audits/audit.jsonl` |
| §4.3 | SC1 resilience: δ ≤ ε and τrec ≤ τmax → sc1 bit | `lmeas/metrics.py::sc1_evaluate`; `cli/main.py::omega_power_sag` | `ldtc omega-power-sag --config configs/profile_r0.yml --drop 0.3 --duration 10` | `audit.jsonl`; `verification_timeline.png`; `sc1_table.csv` |
| §4.1 (Δt); §4.5 | LREG + Δt governance | `guardrails/lreg.py`; `guardrails/dt_guard.py`; `guardrails/audit.py` | `ldtc run --config configs/profile_r0.yml` | `audit.jsonl` with `dt_changed`; hash chain |
| §4.6 Box‑1a | Smell‑tests / invalidations | `guardrails/smelltests.py` | Neg. controls configs | `audit.jsonl` `run_invalidated` with reason |
| §6.2.1 | Refusal semantics (T1–T3) | `arbiter/refusal.py`; `cli/main.py::omega_command_conflict` | `ldtc omega-command-conflict --config configs/profile_negative_command_conflict.yml --observe 2` | `audit.jsonl` `refusal_event` |
| App. A | Derived device‑signed indicators only | `attest/indicators.py`; `attest/exporter.py` | Produced automatically; `python scripts/verify_indicators.py` | JSONL + CBOR; signature verified |
| §4.1 (C/Ex); §4.6 | Deterministic C/Ex partition | `lmeas/partition.py` | `ldtc run --config configs/profile_r0.yml` | `audit.jsonl` flips; Ω freeze |
| §6.5 | Ω battery primitives | `omega/power_sag.py`; `omega/ingress_flood.py` | Ω commands | `audit.jsonl` Ω events; figures bundle |
| Methods §8.6 | Calibration to R* thresholds | `scripts/calibrate_rstar.py` | `python scripts/calibrate_rstar.py ...` | `configs/profile_rstar.yml`; summary JSON |
