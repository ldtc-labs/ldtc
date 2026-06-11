# Paper to code (crosswalk)

A row-by-row map from each section / box of the manuscript to
concrete code, the command that exercises it, and the artifact it
produces. The point of this page is "given a paper claim, where do
I look in the repo?" and "given a CI run, which paper claim is
this artifact evidence for?"

!!! note "Paper sections"
    References are by section *name* in `paper/main.tex` of the
    [accompanying manuscript](https://doi.org/10.5281/zenodo.17073880),
    not by number, because section numbers shift between revisions.

| Paper section / box | Short text | Files / functions | Command | Artifact produced |
| ------------------- | ---------- | ----------------- | ------- | ----------------- |
| Formal Criterion (NC1) | NC1 loop-dominance: `M (dB) ≥ Mmin → nc1` bit | [`m_db`][ldtc.lmeas.metrics.m_db]; [`estimate_L`][ldtc.lmeas.estimators.estimate_L]; [`run_baseline`][ldtc.cli.main.run_baseline] | `ldtc run --config configs/profile_r0.yml` | `artifacts/indicators/ind_*.{jsonl,cbor}`; `artifacts/audits/audit.jsonl` |
| Formal Criterion (SC1) | SC1 resilience: `δ ≤ ε` and `τ_rec ≤ τ_max → sc1` bit | [`sc1_evaluate`][ldtc.lmeas.metrics.sc1_evaluate]; [`omega_power_sag`][ldtc.cli.main.omega_power_sag] | `ldtc omega-power-sag --config configs/profile_r0.yml --drop 0.3 --duration 10` | `audit.jsonl`; `verification_timeline.png`; `sc1_table.csv` |
| Formal Criterion (`Δt`); Measurement & Attestation Guardrails | LREG and `Δt` governance | [`LREG`][ldtc.guardrails.lreg.LREG]; [`DeltaTGuard`][ldtc.guardrails.dt_guard.DeltaTGuard]; [`AuditLog`][ldtc.guardrails.audit.AuditLog] | `ldtc run --config configs/profile_r0.yml` | `audit.jsonl` with `dt_changed`; hash chain |
| Smell-tests & run-invalidation rules (box) | Smell tests / invalidations | [`smelltests`][ldtc.guardrails.smelltests] | Negative-control configs | `audit.jsonl` `run_invalidated` with reason |
| Blueprint (Threat Model & Refusal Path) | Refusal semantics (T1 to T3) | [`refusal`][ldtc.arbiter.refusal]; [`omega_command_conflict`][ldtc.cli.main.omega_command_conflict] | `ldtc omega-command-conflict --config configs/profile_negative_command_conflict.yml --observe 2` | `audit.jsonl` `refusal_event` |
| Appendix A | Derived device-signed indicators only | [`build_and_sign`][ldtc.attest.indicators.build_and_sign]; [`IndicatorExporter`][ldtc.attest.exporter.IndicatorExporter] | Produced automatically; `python scripts/verify_indicators.py` | JSONL + CBOR; signature verified |
| Formal Criterion (C/Ex partition); Smell-tests & run-invalidation rules | Deterministic C/Ex partition | [`PartitionManager`][ldtc.lmeas.partition.PartitionManager]; [`greedy_suggest_C`][ldtc.lmeas.partition.greedy_suggest_C] | `ldtc run --config configs/profile_r0.yml` | `audit.jsonl` `partition_flip`; `Ω` freeze |
| Simulation Study: Methods (Study battery) | `Ω` battery primitives | [`omega.power_sag`][ldtc.omega.power_sag]; [`omega.ingress_flood`][ldtc.omega.ingress_flood]; [`omega.command_conflict`][ldtc.omega.command_conflict] | `ldtc omega-*` commands | `audit.jsonl` `omega_event`; figures bundle |
| Simulation Study: Methods / Results (Threshold calibration) | Calibration to R\* thresholds | `scripts/calibrate_rstar.py` | `make calibrate` | `configs/profile_rstar.yml`; `artifacts/calibration/rstar_summary.json` |
| Results (The criterion separates the controls) | Multi-seed battery: positive vs. negative controls, subsidy invalidation, SC1, refusal | `scripts/study.py` | `make study` | `artifacts/study/study_results.{json,csv,tex}`; `artifacts/study/figures/fig_nc1_contrast.*` |
| Results (The contrast is robust) | NC1 contrast across estimator / lag / window / coupling sweeps | `scripts/sensitivity.py` | `make sensitivity` | `artifacts/sensitivity/sensitivity_results.{csv,tex}`; `artifacts/sensitivity/fig_sensitivity.*` |

## How to read a row

Take the first row, NC1, as an example:

- The paper defines NC1 as `M (dB) ≥ Mmin`, window-by-window.
- That definition is implemented by
  [`m_db`][ldtc.lmeas.metrics.m_db] (which computes
  `10 · log₁₀(𝓛_loop / 𝓛_ex)`) and the threshold check inside
  [`run_baseline`][ldtc.cli.main.run_baseline].
- `ldtc run --config configs/profile_r0.yml` exercises the path
  end-to-end on the bundled R0 profile.
- The path produces `artifacts/indicators/ind_*.{cbor,jsonl}`
  (signed) and `artifacts/audits/audit.jsonl` (hash-chained).
  Reading the `nc1` field of any indicator tells you whether NC1
  passed for that audit-chain head.

The other rows follow the same shape: paper claim → code →
command → file you can grep.

## Where to find the supporting tests

| Concern | Test files |
| ------- | ---------- |
| `m_db` and `sc1_evaluate` | `tests/test_metrics.py`, `tests/test_sc1.py` |
| Estimators (linear / MI / Kraskov) | `tests/test_estimators.py`, `tests/test_estimators_properties.py` |
| Partition manager and greedy growth | `tests/test_partition.py` |
| LREG enclave invariants | `tests/test_lreg.py` |
| Audit-chain integrity | `tests/test_audit_chain.py` |
| Smell tests | `tests/test_smelltests.py` |
| Indicator signing and exporter | `tests/test_attest.py`, `tests/test_exporter.py` |
| Refusal arbiter | `tests/test_refusal.py` |
| `Δt` governance | `tests/test_dt_guard.py` |
| `Ω` modules | `tests/test_omega_*.py` |
| CLI orchestration | `tests/test_cli_*.py` |

(Run `pytest -q` to execute the full suite.)

## See also

- [Architecture](architecture.md): the static module map.
- [Lifecycle](lifecycle.md): the dynamic order of operations.
- [Definitions](definitions.md): the formal statement of every
  symbol used here.
