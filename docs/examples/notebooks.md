# Notebooks

Three reference notebooks live under `notebooks/` in the
repository. They walk through the same NC1 / SC1 / partition
checks as the CLI but render them inline with plots so you can
read each step.

| Notebook | Topic | What it shows |
| -------- | ----- | -------------- |
| `01_verify_nc1.ipynb` | Baseline NC1 verification | Calls [`run_baseline`][ldtc.cli.main.run_baseline] equivalents in cells, plots `M (dB)` per window with `Mmin` rule, prints the signed indicator payload. |
| `02_sc1_omega.ipynb` | SC1 via `Ω` power sag | Reproduces an `Ω` window, overlays `𝓛_loop` recovery, computes `δ` and `τ_rec`, calls [`sc1_evaluate`][ldtc.lmeas.metrics.sc1_evaluate]. |
| `03_partition_sanity.ipynb` | Partition sanity checks | Exercises [`PartitionManager`][ldtc.lmeas.partition.PartitionManager] and [`greedy_suggest_C`][ldtc.lmeas.partition.greedy_suggest_C]; plots before / after `(C, Ex)` membership. |

## Running locally

Install the package in editable mode (notebooks import from
`ldtc.*`) and start Jupyter:

```bash
pip install -e ".[dev]"
jupyter lab
```

Then open the notebooks in the order above. Each notebook starts
with a small "set up the harness" cell that mirrors what
`ldtc run` does internally; if you have already done a CLI run,
the notebook will happily read from your existing
`artifacts/audits/audit.jsonl`.

## Tips

- All three notebooks honor `seed`, `seed_py`, and `seed_np` from
  the bundled R0 profile, so re-runs reproduce the same plots.
- The plotting cells reuse the same theme as the CLI bundle; see
  [Reporting](../guides/reporting.md) for the palette and
  matplotlib `rcParams`.
- If a cell raises a smell-test exception, that is not a bug; it
  is the harness telling you the run was invalidated. Read the
  audit log alongside the notebook output.

## See also

- [Minimal run](minimal.md): a non-interactive equivalent.
- [Runs](../guides/runs.md): the corresponding CLI commands.
- [Definitions](../concepts/definitions.md): every symbol the
  notebooks use.
