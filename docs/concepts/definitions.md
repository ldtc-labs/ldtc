# Definitions

This page is the authoritative glossary for every symbol used in
the LDTC code, audit log, and accompanying manuscript. Each entry
gives:

- A short formal statement (math or pseudocode).
- A plain-English gloss.
- The paper section that defines it.
- A link to the API symbol that implements or measures it.

The goal is that anyone reading the paper, the audit log, or the
source can map a symbol to *exactly one* canonical meaning.

!!! note "Paper sections"
    Section references point at `paper/main.tex` in the
    [accompanying manuscript](https://doi.org/10.5281/zenodo.17073880).
    They are reproduced here for convenience; the paper is the
    normative source.

## Time and sampling

### `Δt`: scheduler period

**Formal.** `Δt ∈ ℝ_{>0}` is the fixed sampling period of the
real-time tick, in seconds. The scheduler's effective rate is
`f = 1 / Δt`. Changes to `Δt` at runtime are rate-limited to at
most `max_dt_changes_per_hour` and always require a privileged
edit through
[`DeltaTGuard.change_dt`][ldtc.guardrails.dt_guard.DeltaTGuard.change_dt],
gated by
[`DeltaTGuard.can_change`][ldtc.guardrails.dt_guard.DeltaTGuard.can_change].

**Plain English.** How often the controller wakes up. Holding `Δt`
constant is what lets `M` and `τ_rec` mean the same thing across
runs.

**Paper.** "Formal Criterion" (sampling-window constraints) and
"Measurement & Attestation Guardrails" (Δt governance and audit).

**API.** [`FixedScheduler`][ldtc.runtime.scheduler.FixedScheduler],
[`DeltaTGuard`][ldtc.guardrails.dt_guard.DeltaTGuard].

### `W`: window length

**Formal.** `W = ⌈window_sec / Δt⌉` consecutive samples form one
analysis window. `𝓛` and `M` are computed once per window.

**Plain English.** How much history each estimator sees. Smaller
`W` means tighter time resolution but noisier estimates; larger
`W` means smoother estimates but slower SC1 reaction.

**Paper.** "Formal Criterion" (estimators, sampling window).

**API.** [`SlidingWindow`][ldtc.runtime.windows.SlidingWindow].

## Loop and exchange influence

### `C`, `Ex`: partition

**Formal.** Given `N` measured signals indexed `0..N-1`, the
partition is a pair `(C, Ex)` of disjoint index sets with
`C ∪ Ex = {0..N-1}`. `C` is the closed-loop ("controller") set
and `Ex` is the exchange ("environment") set. Updates are managed
by [`PartitionManager`][ldtc.lmeas.partition.PartitionManager],
which applies hysteresis (a candidate `C'` is accepted only after
yielding `ΔM ≥ delta_dB_min` for `consec` consecutive windows).
The partition is **frozen** during `Ω` windows so SC1 cannot be
gamed by reshuffling membership.

**Plain English.** Which signals count as part of the loop, and
which count as the world the loop is talking to.

**Paper.** "Formal Criterion" (deterministic C/Ex partitioning) and
"Smell-tests & run-invalidation rules" (partition stability).

**API.** [`Partition`][ldtc.lmeas.partition.Partition],
[`PartitionManager`][ldtc.lmeas.partition.PartitionManager],
[`greedy_suggest_C`][ldtc.lmeas.partition.greedy_suggest_C].

### `𝓛_loop`, `𝓛_ex`: loop and exchange influence

**Formal.** For a window `X ∈ ℝ^{T × N}` and partition `(C, Ex)`:

- `𝓛_loop(X) = mean over (i, j) ∈ C × C with i ≠ j of  L̂(X[:, i] → X[:, j])`
- `𝓛_ex(X)   = mean over (i, j) ∈ Ex × C of            L̂(X[:, i] → X[:, j])`

`L̂(·)` is one of three predictive-dependence estimators selected by
the `method` config field:

- `method = "linear"`: lagged Granger-like log-likelihood ratio.
- `method = "mi"`: sklearn `mutual_info_regression` at lag
  `mi_lag`.
- `method = "mi_kraskov"`: Kraskov k-NN mutual information with
  `k = mi_k`.

Each window also produces a 95% CI from a circular block bootstrap
of length `n_boot`.

**Plain English.** "How much do the loop signals predict each
other?" versus "How much does the environment predict the loop?"

**Paper.** "Formal Criterion" (estimators); "Measurement &
Attestation Guardrails".

**API.** [`estimate_L`][ldtc.lmeas.estimators.estimate_L],
[`LResult`][ldtc.lmeas.estimators.LResult].

### `M`, `Mmin`: loop-dominance margin

**Formal.** `M = 10 · log₁₀(𝓛_loop / 𝓛_ex)` in decibels, computed
per window with a small `eps = 1e-12` floor on numerator and
denominator to avoid `log10(0)`. `Mmin` is the NC1 acceptance
threshold (config field `Mmin_db`, default `3.0`).

**Plain English.** How many decibels louder the loop is than the
environment. A run passes NC1 if `M ≥ Mmin` window-by-window for
the baseline.

**Paper.** "Formal Criterion" (Necessary Condition, NC1).

**API.** [`m_db`][ldtc.lmeas.metrics.m_db].

### `Mq`: quantized `M` (6 bit)

**Formal.** `Mq = clamp(round(M / 0.25), 0, 63)`. Encodes `M`
values in `[0, 15.75] dB` at 0.25 dB resolution. This is what
appears in the signed indicator payload, never the raw `M`.

**Plain English.** A small, lossy summary of `M` that can leave
the LREG enclave.

**Paper.** "Measurement & Attestation Guardrails"; Appendix A.

**API.** [`quantize_M`][ldtc.attest.indicators.quantize_M].

## SC1 evaluation

### `δ`: fractional drop during `Ω`

**Formal.** `δ = max(0, (𝓛_loop_baseline − 𝓛_loop_trough) /
𝓛_loop_baseline)` where `𝓛_loop_trough` is the minimum of
`𝓛_loop` measured during the `Ω` window.

**Plain English.** "By what fraction did the loop influence dip
under the perturbation?"

**Paper.** "Formal Criterion" (Sufficient Condition, SC1).

**API.** [`SC1Stats.delta`][ldtc.lmeas.metrics.SC1Stats],
[`sc1_evaluate`][ldtc.lmeas.metrics.sc1_evaluate].

### `ε`: tolerance on `δ`

**Formal.** `ε ∈ [0, 1]` is the maximum allowed fractional drop.
A run satisfies the SC1 dip clause when `δ ≤ ε`.

**Plain English.** How big a dip we are willing to tolerate
before we call SC1 a failure. Default `ε = 0.15` (15%).

**Paper.** "Formal Criterion" (Sufficient Condition, SC1);
"Simulation Study: Methods" (Threshold calibration).

**API.** `epsilon` config field; consumed by
[`sc1_evaluate`][ldtc.lmeas.metrics.sc1_evaluate].

### `τ_rec`, `τ_max`: recovery time and budget

**Formal.** `τ_rec` is the elapsed time, in seconds, from the end
of the `Ω` window to the first window in which `𝓛_loop` returns
to `𝓛_loop_baseline · (1 − ε)`. SC1 requires
`τ_rec ≤ τ_max` (default `τ_max = 60.0 s`).

**Plain English.** How long the loop took to bounce back. SC1
fails if it took too long.

**Paper.** "Formal Criterion" (Sufficient Condition, SC1).

**API.** [`SC1Stats.tau_rec`][ldtc.lmeas.metrics.SC1Stats],
[`sc1_evaluate`][ldtc.lmeas.metrics.sc1_evaluate].

### `M_post`: post-recovery margin

**Formal.** `M` measured after the recovery gate. SC1 additionally
requires `M_post ≥ Mmin`, i.e. the loop must come back *and* still
pass NC1.

**Plain English.** "Did we recover all the way?"

**Paper.** "Formal Criterion" (Sufficient Condition, SC1).

**API.** [`SC1Stats.M_post`][ldtc.lmeas.metrics.SC1Stats].

### NC1, SC1: the two indicator bits

**Formal.**

- `NC1 = 1` iff the most recent measured window satisfied
  `M ≥ Mmin` (and the run is not invalidated).
- `SC1 = 1` iff the most recent `Ω` trial satisfied
  `(δ ≤ ε) ∧ (τ_rec ≤ τ_max) ∧ (M_post ≥ Mmin)`.

Both are exported as 1-bit booleans in the signed indicator
payload alongside `Mq`, the run counter, and the audit chain head.

**Paper.** "Formal Criterion" (NC1, SC1); Appendix A.

**API.** [`build_and_sign`][ldtc.attest.indicators.build_and_sign],
[`IndicatorExporter`][ldtc.attest.exporter.IndicatorExporter].

## Perturbations

### `Ω`: perturbation event

**Formal.** A labeled, time-bounded intervention applied to the
plant during a known interval `[t₀, t₁]`. The CLI tags the audit
log with `omega_event` records and freezes the partition for the
duration. The shipped battery is:

| Module | What it does |
| ------ | ------------ |
| [`omega.power_sag`][ldtc.omega.power_sag] | Drops the harvest term `H` by a fraction. |
| [`omega.ingress_flood`][ldtc.omega.ingress_flood] | Multiplies external demand for a window. |
| [`omega.command_conflict`][ldtc.omega.command_conflict] | Issues a risky `hard_shutdown`; the arbiter's refusal latency `T_refuse` is recorded. |

**Plain English.** Each `Ω` is a controlled "kick" we apply to see
whether the loop survives.

**Paper.** "Blueprint" (Verification Pipeline); "Predicted Observable
Signatures" (Pass/Fail tables).

**API.** [`ldtc.omega`][ldtc.omega].

### `T_refuse`: refusal latency

**Formal.** Wall-clock seconds between issuing a risky command and
the arbiter's refusal record being appended to the audit. Captured
by
[`RefusalArbiter.decide`][ldtc.arbiter.refusal.RefusalArbiter.decide]
when `M < Mmin` and the survival bit is asserted.

**Paper.** "Blueprint" (Threat Model & Refusal Path); "Predicted
Observable Signatures" (Pass/Fail tables).

**API.** [`ldtc.arbiter.refusal`][ldtc.arbiter.refusal].

## Guardrails and audit

### LREG: loop registry enclave

**Formal.** A process-local, write-only registry that stores raw
`𝓛_loop`, `𝓛_ex`, and CI bounds per window. The
[`LREG.derive`][ldtc.guardrails.lreg.LREG.derive] method returns
*only* the sanctioned derived fields (`M_db`, `nc1`, `counter`,
`invalidated`). Direct iteration over the registry is intentionally
unavailable; CSV exporters and indicator builders both call
[`smelltests.audit_contains_raw_lreg_values`][ldtc.guardrails.smelltests.audit_contains_raw_lreg_values]
to ensure no raw `𝓛` ever leaks.

**Plain English.** The black box. Raw measurements go in; only
indicators come out.

**Paper.** "Measurement & Attestation Guardrails" (LREG).

**API.** [`LREG`][ldtc.guardrails.lreg.LREG].

### Audit log: hash-chained event journal

**Formal.** Append-only JSONL where each record contains a
monotone counter, a payload, and `prev_hash = SHA256(prev_record)`.
[`audit_chain_broken`][ldtc.guardrails.smelltests.audit_chain_broken]
re-reads the file from disk after the run and returns `True` on
any mismatch. Broken chains invalidate the run via
[`smelltests`][ldtc.guardrails.smelltests].

**Plain English.** A tamper-evident receipt of every event the
harness saw, in order.

**Paper.** "Measurement & Attestation Guardrails" (audit and attestation).

**API.** [`AuditLog`][ldtc.guardrails.audit.AuditLog].

### Smell tests and invalidations

**Formal.** A run is invalidated (the audit emits
`run_invalidated` and the next exported indicator carries
`invalidated = true`) when any of:

- **CI inflation:** the CI half-width on `𝓛_loop` or `𝓛_ex`
  exceeds `0.30` for a window
  ([`invalid_by_ci`][ldtc.guardrails.smelltests.invalid_by_ci]).
- **Excessive `Δt` edits:** more than 3 `Δt` changes in any
  rolling hour, enforced inline by the
  [`DeltaTGuard`][ldtc.guardrails.dt_guard.DeltaTGuard] which
  refuses changes once the rolling cap is reached.
- **Partition flapping:** more than 2 C/Ex flips per hour with
  dynamic regrow enabled.
- **Export breach:** an attempt to write a CSV row containing raw
  `𝓛` fields.
- **Subsidy flag:** sustained `M` increase while I/O or SoC rises
  without a logged harvest event.
- **Audit chain broken:** `prev_hash` mismatch detected post-run.

**Paper.** "Smell-tests & run-invalidation rules" (box).

**API.** [`ldtc.guardrails.smelltests`][ldtc.guardrails.smelltests].

## Profiles and reproducibility

### `profile_id`: R0 vs R\*

**Formal.** A `u8` discriminator carried in every signed
indicator. `0 = R0` (default thresholds), `1 = R*` (calibrated
per-device thresholds), `2..255 = reserved`. Set in `configs/*.yml`
under `profile_id`.

**Paper.** "Simulation Study: Methods" (Threshold calibration).

**API.** [`IndicatorConfig.profile_id`][ldtc.attest.indicators.IndicatorConfig].

### `seed`: deterministic RNG

**Formal.** Each run config carries `seed`, `seed_py`, and
`seed_np` integers. The CLI seeds Python's `random`, NumPy's
default RNG, and the bootstrap RNG used inside
[`estimate_L`][ldtc.lmeas.estimators.estimate_L]. Two runs with the
same seed and config produce bit-identical audit logs (modulo
wall-clock timestamps).

**Paper.** "Simulation Study: Methods" (measurement configuration, seeds).

## Notation summary

A quick visual reference of the symbols used throughout the docs
and code:

| Symbol | Code field | Meaning |
| ------ | ---------- | ------- |
| `Δt` | `dt` | Scheduler period (s). |
| `W` | `window_sec` | Window length in seconds. |
| `N` | `N_signals` | Number of measured signals. |
| `C`, `Ex` | `partition.C`, `partition.Ex` | Loop / exchange index sets. |
| `𝓛_loop` | `LResult.L_loop` | Mean loop predictive influence per window. |
| `𝓛_ex` | `LResult.L_ex` | Mean exchange predictive influence per window. |
| `M` | `M_db` | `10 · log₁₀(𝓛_loop / 𝓛_ex)`, in dB. |
| `Mmin` | `Mmin_db` | NC1 threshold, in dB. |
| `Mq` | `mq` | 6-bit quantized `M`. |
| `δ` | `delta` | Fractional `𝓛_loop` drop during `Ω`. |
| `ε` | `epsilon` | Tolerance on `δ`. |
| `τ_rec` | `tau_rec` | Recovery time, in seconds. |
| `τ_max` | `tau_max` | SC1 recovery budget, in seconds. |
| `T_refuse` | `T_refuse` | Refusal latency, in seconds. |
| `Ω` | `omega_event` | Labeled perturbation interval. |

## Next steps

- Read the [mental model](mental-model.md) for the one-paragraph
  story these symbols tell.
- See the [paper-to-code crosswalk](paper-to-code.md) for the
  per-section mapping.
- Jump into [`ldtc.lmeas`](../api/lmeas.md) and
  [`ldtc.attest`](../api/attest.md) to read the implementations.
