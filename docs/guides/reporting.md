# Reporting and figures

After a run, the CLI invokes
[`reporting.artifacts.bundle`][ldtc.reporting.artifacts.bundle]
automatically. This guide covers what that bundle contains and how
to regenerate or extend it.

## What's in a bundle

For each invocation, `bundle()` writes the following into
`artifacts/figures/`:

| File | Produced by | Purpose |
| ---- | ----------- | ------- |
| `timeline_<eta>_<ts>.png` | [`render_paper_timeline`][ldtc.reporting.timeline.render_paper_timeline] | Paper-style timeline: normalized `𝓛_loop`, `𝓛_ex`, `M (dB)` with `Mmin` rule, shaded `Ω` window, audit-event tick rug, profile / hash footer. |
| `timeline_<eta>_<ts>.svg` | same | Vector version of the timeline. |
| `sc1_table_<eta>_<ts>.csv` (optional) | [`write_sc1_table`][ldtc.reporting.tables.write_sc1_table] | Per-trial SC1 results: `eta, delta, tau_rec, M_post, pass`. Only written when at least one `sc1_result` audit row exists. |
| `manifest_<eta>_<ts>.json` | `bundle()` | Profile id, thresholds (`Δt`, `window_sec`, `Mmin`, `ε`, `τ_max`), seeds, audit hash head, `ind_*` schema, public-key SHA-256, list of artifacts. |
| `config_snapshot_<eta>_<ts>_<name>.yml` (optional) | `bundle()` | Verbatim copy of the config file used for the run. |
| `NOTICE_<eta>_<ts>.txt` | `bundle()` | One-line policy notice that no raw `𝓛` is in any artifact. |

`<eta>` is the `Ω` kind (`baseline`, `power_sag`, `ingress_flood`,
`command_conflict`, `exogenous_subsidy`); `<ts>` is the Unix
timestamp at bundle time.

All produced files are `chmod`-ed to read-only (`0o444`) on
POSIX-like filesystems by
[`bundle`][ldtc.reporting.artifacts.bundle] so a results
directory is hard to mutate after the fact. On Windows this is a
best-effort no-op.

## Regenerating a bundle from an audit log

The bundle is a pure function of the audit JSONL plus the public
key file, so you can regenerate it any time:

```bash
python -c "from ldtc.reporting.artifacts import bundle; print(bundle('artifacts/figures', 'artifacts/audits/audit.jsonl'))"
```

`bundle()` always scopes itself to the most recent `run_header`
record in the audit, so re-runs in a shared file do not
contaminate each other's artifacts.

## Reading the manifest

The manifest is the single most useful file for downstream tooling
or paper supplements:

```json
{
  "version": 1,
  "profile_id": 0,
  "profile": "R0",
  "config_path": "configs/profile_r0.yml",
  "dt": 0.01,
  "window_sec": 0.2,
  "method": "linear",
  "p_lag": 3,
  "mi_lag": 1,
  "Mmin_db": 3.0,
  "epsilon": 0.15,
  "tau_max": 60.0,
  "seed_py": 12345,
  "seed_np": 12345,
  "eta": "power_sag",
  "eta_args": {"drop": 0.3, "duration": 10.0},
  "ci_coverage": 0.95,
  "audit_hash_head": "<hex>",
  "indicator_schema": {"mq_step_db": 0.25, "mq_bits": 6},
  "pubkey_sha256": "<hex>",
  "policy_note": "No raw LREG values or CI bounds are exported; ...",
  "artifacts": {
    "timeline_png": "...png",
    "timeline_svg": "...svg",
    "sc1_table_csv": "...csv"
  }
}
```

Useful properties:

- `audit_hash_head` matches the `audit_prev_hash` of the next
  signed indicator written after the bundle, anchoring the
  bundle to the same chain a verifier checks.
- `pubkey_sha256` is a fingerprint of the device public key, so
  you can check that a bundle was produced under the expected
  device without bundling the key itself.
- `eta` and `eta_args` reproduce the exact `Ω` invocation, so
  someone with the config and the seeds can reproduce the run
  bit-for-bit (modulo wall-clock timestamps).

## Extending the timeline

The timeline renderer reads only the audit log; it does not have
access to raw `𝓛`. To add a new trace, append the relevant
*derived* quantity into the audit (for example a moving-average
`M (dB)` or a feature-engineered diagnostic) and extend
[`render_paper_timeline`][ldtc.reporting.timeline.render_paper_timeline]
to consume it.

A typical extension flow:

1. Decide what derived quantity you want to plot.
2. Append it as a new audit event type from inside the CLI tick
   (for example `audit.append("custom_metric", {"value": ...})`).
3. In a fork of `reporting/timeline.py`, parse the new event into
   a per-window series and `ax.plot(...)` it.
4. Re-run `bundle()` to regenerate the figure.

## Style and color palette

The timeline uses a consistent, paper-friendly palette and
matplotlib theme defined in
[`ldtc.reporting.style`][ldtc.reporting.style]. Reuse them when
building bespoke figures so multiple plots in a paper match.

```python
import matplotlib.pyplot as plt
from ldtc.reporting.style import COLORS, apply_matplotlib_theme

apply_matplotlib_theme()
fig, ax = plt.subplots()
ax.plot(t, m_db, color=COLORS["blue"], label="M (dB)")
ax.axhline(Mmin, color=COLORS["red"], linestyle="--", label="Mmin")
ax.legend()
```

The same palette also drives Graphviz diagrams via
[`apply_graphviz_theme`][ldtc.reporting.style.apply_graphviz_theme]
and the convenience constructor
[`new_graph`][ldtc.reporting.style.new_graph].

## See also

- [`ldtc.reporting`][ldtc.reporting]: full API for the timeline,
  tables, style, and bundle entry points.
- [Indicators](../concepts/indicators.md): what the bundle does
  *not* contain (raw `𝓛`, CIs).
- [Lifecycle](../concepts/lifecycle.md): when in a run the bundle
  is produced.
