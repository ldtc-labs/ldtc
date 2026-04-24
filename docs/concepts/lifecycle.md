# Lifecycle of a run

This page traces a single `ldtc run --config configs/profile_r0.yml`
invocation from process startup to the last `chmod` on the manifest.
If you understand this page, you can read any audit log produced by
the harness without surprises.

## Phase 0: process startup

| Step | Code |
| ---- | ---- |
| Parse `--config`. | [`_load_yaml`][ldtc.cli.main] |
| Seed Python `random` and NumPy from `seed`, `seed_py`, `seed_np`. | `_set_seeds` |
| Resolve `dt`, `window_sec`, `method`, `Mmin_db`, partition hysteresis knobs, etc. | `run_baseline` body |
| Create `artifacts/{audits,indicators,figures,keys}` if absent. | `_ensure_dirs` |
| Open the audit log (`artifacts/audits/audit.jsonl`, append-only). | [`AuditLog`][ldtc.guardrails.audit.AuditLog] |
| Append `baseline_start` and a `run_header` record (config path, seeds, thresholds, `Δt`, `Ω` kind). | `audit.append` |
| Construct the plant adapter. | [`_make_adapter_from_profile`][ldtc.cli.main] |
| Allocate `SlidingWindow`, `PartitionManager`, `LREG`, `RefusalArbiter`, `ControllerPolicy`, `IndicatorExporter`, `IndicatorConfig`. | (constructors) |
| Load or generate Ed25519 keys under `artifacts/keys/`. | [`ensure_keys`][ldtc.attest.keys.ensure_keys] |

The `run_header` is the single most useful audit record for
reviewers: it captures every knob that affects the outcome.

## Phase 1: the steady-state tick

The scheduler runs the tick closure in a daemon thread every `Δt`
seconds. One tick is roughly:

```python
def tick(_now: float) -> None:
    state = adapter.read_state()
    predicted = lreg.latest().M_db if lreg.latest() else 0.0
    action = policy.compute(state, predicted_M_db=predicted, risky_cmd=risky_cmd)
    adapter.write_actuators(action)
    sw.append(adapter.read_state())

    if sw.ready():
        X = np.asarray(sw.get_matrix())
        part = pm.get()
        res = estimate_L(X, part.C, part.Ex, method=..., p=..., n_boot=...)
        diag = stationarity_checks(X); vratio = var_nt_ratio(...)
        audit.append("window_diagnostics", diag)
        M = m_db(res.L_loop, res.L_ex)
        nc1 = M >= Mmin
        if invalid_by_ci(res.ci_loop, res.ci_ex, cfg_smell):
            lreg.invalidate("ci_inflation"); audit.append("run_invalidated", ...)
        lreg.write(LEntry(L_loop=res.L_loop, L_ex=res.L_ex, M_db=M, nc1_pass=nc1, ...))
        audit.append("window_measured", {"M_db": M, "nc1": nc1, ...})

        if window_idx % part_growth_cadence_windows == 0:
            cand = greedy_suggest_C(X, part.C, lambda_=..., theta=..., kappa=...)
            pm.maybe_regrow(cand, delta_M_db=...,
                            delta_M_min_db=part_delta_M_min_db,
                            consecutive_required=part_consecutive_required)

        derived = lreg.derive()
        exporter.maybe_export(priv, audit, derived, icfg,
                              last_sc1_pass=...)  # rate-limited to 2 Hz
```

Important properties:

- `lreg.latest()` and `lreg.derive()` are the *only* exits from
  the enclave. Code paths that need raw `𝓛` for an internal
  decision (for example the trough tracker in `omega_power_sag`)
  read it inside the same tick and never persist it.
- Every smell-test invalidation appends both a `run_invalidated`
  record *and* sets a flag inside `LREG`, so the next exported
  indicator carries `invalidated = true`. The audit log and the
  signed indicator agree by construction.
- The `IndicatorExporter` is rate-limited (default 2 Hz) so the
  signed-indicator stream stays bounded regardless of `Δt`.

## Phase 2: optional `Ω` window

For the `omega-*` subcommands the loop above runs first as a
"baseline" phase, then transitions through three phases tracked by
a `phase` variable:

```text
baseline ──► omega ──► recovery ──► (terminal)
            ^         ^
       partition.    partition.
       freeze()      unfreeze()
```

While in the `omega` phase:

1. The CLI calls
   [`adapter.apply_omega(name, **kwargs)`][ldtc.plant.adapter.PlantAdapter.apply_omega],
   which delegates to the relevant module in
   [`ldtc.omega`][ldtc.omega] (for example
   [`omega.power_sag.apply`][ldtc.omega.power_sag.apply]).
2. An `omega_event` record is appended to the audit log with the
   kind, parameters, and start/stop timestamps.
3. The partition manager is frozen so SC1 cannot be gamed by
   reshuffling `(C, Ex)`.
4. Estimators continue to fire each window. The minimum
   `𝓛_loop` observed during the window becomes
   `L_loop_trough`.

When the `Ω` window ends:

1. The partition is unfrozen.
2. The CLI watches for the first window that satisfies the SC1
   recovery gate (`𝓛_loop ≥ baseline · (1 − ε)`), holding for
   `sustained_required_windows` consecutive windows. The elapsed
   time becomes `τ_rec`.
3. [`sc1_evaluate`][ldtc.lmeas.metrics.sc1_evaluate] is called
   with `(L_loop_baseline, L_loop_trough, L_loop_recovered,
   M_post, ε, τ_rec, Mmin, τ_max)`; the boolean decision becomes
   the next `SC1` indicator bit.
4. An `sc1_evaluated` audit record is appended with the stats
   dict (`delta`, `tau_rec`, `M_post`, `passed`).

Command-conflict trials add a fifth ingredient: the CLI issues a
risky command (typically `hard_shutdown`), the
[`RefusalArbiter`][ldtc.arbiter.refusal.RefusalArbiter] refuses
when `M < Mmin`, and `T_refuse` is measured from the audit
timestamps.

## Phase 3: scheduler stop and post-run checks

The CLI sleeps for the requested run length (`baseline_sec`,
default `10 s`) and then enters the `finally` block:

| Step | Code |
| ---- | ---- |
| Stop the scheduler and capture jitter stats. | `sch.stop()` |
| Append `baseline_stop` (or `omega_*_stop`) with `ticks`. | `audit.append` |
| If `p95(|jitter|) / Δt > jitter_p95_rel_max`, append `dt_jitter_excess`. | [`SmellConfig`][ldtc.guardrails.smelltests.SmellConfig] |
| Re-validate the audit chain on disk. | [`audit_chain_broken`][ldtc.guardrails.smelltests.audit_chain_broken] |
| Re-scan the audit for raw `𝓛` leakage. | [`audit_contains_raw_lreg_values`][ldtc.guardrails.smelltests.audit_contains_raw_lreg_values] |
| Print the invalidation footer. | `_print_invalidation_footer` |

Either smell test failing here will append a final
`run_invalidated` record. Subsequent exporters and reporters
respect that flag.

## Phase 4: artifact bundle

Once the audit is closed, the CLI calls
[`reporting.artifacts.bundle`][ldtc.reporting.artifacts.bundle],
which:

1. Reads the audit log start to end.
2. Renders the timeline figure
   ([`render_paper_timeline`][ldtc.reporting.timeline.render_paper_timeline])
   in PNG and SVG: normalized `𝓛_loop` and `𝓛_ex`, `M (dB)`
   with an `Mmin` rule, an `Ω` shaded band, and a tick rug for
   audit events. The footer carries the profile and the audit
   hash head.
3. Renders the SC1 summary table
   ([`write_sc1_table`][ldtc.reporting.tables.write_sc1_table])
   if at least one `sc1_evaluated` record exists.
4. Writes the manifest JSON (profile id, thresholds, audit head,
   public-key SHA-256, list of artifacts).
5. Sets POSIX read-only permissions on every produced file (the
   `chmod` is performed inline by
   [`bundle`][ldtc.reporting.artifacts.bundle]).
6. Appends a `report_generated` audit record with the basenames.

Finally the CLI prints a one-line summary:

```
Bundle: timeline=<...png>, table=<...csv>, manifest=<...json>
```

That is the entire lifecycle. Re-running the same command with the
same seeds (and `make clean-artifacts`) produces a byte-identical
audit log up to wall-clock timestamps, and bit-identical signed
indicators conditional on those timestamps.

## What you can rely on

- **Audit precedes signing.** Every fact in a signed indicator
  appeared in the audit first. A mismatch is a smell test failure.
- **Indicators are rate-limited.** A 1 kHz `Δt` does not produce
  a 1 kHz indicator stream; the exporter is `2 Hz` by default.
- **Files become read-only.** The bundle's `chmod` step makes it
  hard to silently mutate a manifest after the fact. (On Windows
  this is a best-effort no-op.)
- **The audit chain is verified twice:** once in process and once
  by re-reading the file from disk. A torn write or a partial
  flush still gets caught.

## Next steps

- [Architecture](architecture.md): the static module map.
- [Indicators](indicators.md): the wire format.
- [Guardrails](guardrails.md): the per-test thresholds.
- [`ldtc.cli` API](../api/cli.md): every CLI subcommand by name.
