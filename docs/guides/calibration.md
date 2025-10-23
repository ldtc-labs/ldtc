# Calibration to R* (Methods §8.6)

This repository provides a small synthetic calibration to replace the R0 presets with data-grounded thresholds R* = {Mmin, ε, τmax, σ}.

The script sweeps a baseline window and applies a power-sag Ω battery to estimate:

- Mmin_db: one-sided 95% lower bound of loop-dominance M during quiescent baseline (floor 1 dB)
- ε: tolerance for fractional loop-power depression δ using the 90th percentile across Ω trials plus a small safety margin (capped at 0.25)
- τmax: 95th percentile of measured τrec plus a fixed latency cushion max(3·Δt, 5 s)
- σ: additive margin s.t. Lloop ≥ Lexchange + σ consistent with Mmin and typical Lexchange

## Command

```bash
python scripts/calibrate_rstar.py --dt 0.01 --window-sec 0.25 --method linear --baseline-sec 15 \
  --omega-trials 6 --sag-drop 0.3 --sag-duration 8 --out configs/profile_rstar.yml \
  --summary artifacts/calibration/rstar_summary.json
```

## Outputs

- `configs/profile_rstar.yml` — calibrated profile with thresholds inserted
- `artifacts/calibration/rstar_summary.json` — JSON record of inputs/outputs for the paper supplement

## Reporting

- All figures and tables should state the active profile: set `profile_id` to 0 for R0 or 1 for R* in the YAML used for that run. The CLI embeds `profile_id` in exported indicators.

## Notes

- Calibration runs on the synthetic plant with `seed_C=[E,T,R]` matching the demo. For other plants/settings, re-run calibration.
- The baseline and Ω trials reuse the same estimators used in the CLI, including block bootstrap CIs. Estimator options include a VAR/linear path and mutual information paths (sklearn MI and Kraskov k‑NN/KSG). Optional TE/DI plugin hooks are provided; if no backend is installed, the methods fall back to MI (KSG) as a conservative proxy.

### Mmin(dB) vs σ (relation)

Both encode a margin between `L_loop` and `L_exchange`:

- `Mmin_db` (multiplicative in dB): require `L_loop ≥ L_exchange × 10^(Mmin_db/10)`.
- `σ` (additive): require `L_loop ≥ L_exchange + σ`.

They relate via:

```
σ = (10^(Mmin_db/10) − 1) × L_exchange
```

The calibrator writes `Mmin_db` and derives a consistent `σ` for reporting.
