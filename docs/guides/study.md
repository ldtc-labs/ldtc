# Multi-seed study and results

The study harness (`scripts/study.py`) turns the single-run
verification harness into a reproducible, multi-seed experiment.
It runs the positive control, the negative controls, the SC1
perturbation battery, and the command-conflict refusal scenario
across `N` seeds, parses each run's hash-chained audit log, and
aggregates the per-seed outcomes into machine-readable and
paper-ready tables plus figures.

The study calls the same production CLI handlers a verifier runs,
so it exercises exactly the code paths under test (no separate,
divergent measurement path).

## Run it

```bash
make study          # multi-seed study -> artifacts/study
make sensitivity    # NC1 sensitivity sweeps -> artifacts/sensitivity
make calibrate      # R0 -> R* threshold calibration
make results        # all of the above
```

Or directly, to choose the seed count:

```bash
python scripts/study.py --seeds 15
```

## Scenarios

| Scenario | Type | Expected outcome |
| -------- | ---- | ---------------- |
| Positive control | NC1 | NC1 holds (`M` well above `Mmin`) |
| Controller disabled | NC1 (negative) | NC1 rejected (`M < 0`), run valid |
| Sustained ex-flood (unshielded) | NC1 (negative) | NC1 rejected (`M < 0`), run valid |
| Exogenous subsidy | NC1 (negative) | Run invalidated by the subsidy red flag |
| Power sag | SC1 | Loop dominance recovers |
| Ingress flood | SC1 | Loop dominance recovers |
| Command conflict | Refusal | Risky command refused at low SoC |

## Statistics

The **seed is the unit of replication**:

- Continuous quantities (median `M (dB)`) are summarized by the
  mean of per-seed medians with a percentile **bootstrap** 95% CI.
- Binary outcomes (run validity, NC1 / SC1 pass, refusal) are
  summarized by a proportion with a **Wilson** score 95% CI.

## Outputs

Written to `artifacts/study/`:

- `study_results.json`: full payload (aggregates, per-run rows,
  and run metadata including the exact per-scenario overrides).
- `study_results.csv`: flat aggregate table.
- `study_results.tex`: `booktabs` table for the manuscript.
- `figures/fig_nc1_contrast.{png,pdf,svg}`: per-seed median `M`
  for the positive and negative controls (the headline NC1
  result).
- `figures/fig_outcomes.{png,pdf,svg}`: fraction of seeds whose
  outcome matched the theory's prediction, with Wilson CIs.
- `figures/fig_sc1_recovery.{png,pdf,svg}`: seed-aggregated
  `M(t)` trajectories for the SC1 perturbations.

The sensitivity sweeps (`artifacts/sensitivity/`) show that the
NC1 contrast is robust to the VAR lag `p`, the window length, the
estimator family, and the strength of the plant's internal
coupling.

## See also

- [Calibration (R\*)](calibration.md): how `Mmin`, `ε`, `τ_max`,
  and `σ` are derived from the baseline and `Ω` batteries.
- [Runs and Ω Battery](runs.md): the individual scenarios.
- [Reporting and Figures](reporting.md): the per-run artifact
  bundle.
