# Calibration to R\*

The bundled `R0` profile uses generic thresholds (`Mmin = 3 dB`,
`ε = 0.15`, `τ_max = 60 s`). For a real device, you almost
certainly want **R\***: the same harness, but with thresholds
calibrated from a quiet baseline and a power-sag battery on the
actual hardware (or your specific synthetic plant). This is the
process the manuscript's "Simulation Study: Methods" section
(Threshold calibration) describes.

## What gets calibrated

| Threshold | Meaning | Calibration rule |
| --------- | ------- | ---------------- |
| `Mmin (dB)` | NC1 acceptance margin. | One-sided 95% lower bound of `M (dB)` over the quiescent baseline, floored at `1 dB`. |
| `ε` | SC1 dip tolerance. | 90th percentile of `δ` across `Ω` trials plus a small safety margin (`0.02`), floored at `0.10` and capped at `0.50`. |
| `τ_max` | SC1 recovery budget. | 95th percentile of measured `τ_rec` plus `max(3 · Δt, 5 s)` cushion. |
| `σ` | Additive margin on `𝓛`. | Derived from `Mmin` and the typical `𝓛_ex` so that `𝓛_loop ≥ 𝓛_ex + σ` and `𝓛_loop ≥ 𝓛_ex × 10^(Mmin / 10)` agree. |

`Mmin (dB)` and `σ` encode the same idea in different units:

- `Mmin (dB)` is multiplicative in dB:
  `𝓛_loop ≥ 𝓛_ex · 10^(Mmin / 10)`.
- `σ` is additive: `𝓛_loop ≥ 𝓛_ex + σ`.

The two relate via `σ = (10^(Mmin / 10) − 1) · 𝓛_ex`. The
calibration script writes `Mmin (dB)` into the new profile and
emits a consistent `σ` into the summary JSON for paper-side
reporting.

## Run the calibrator

```bash
python scripts/calibrate_rstar.py \
  --baseline-seeds 6 \
  --sag-seeds 6
```

The calibrator reuses the validated `R0` profile
(`configs/profile_r0.yml`) for all measurement knobs (`Δt`, the
window length, the estimator `method`, `p_lag`, and `n_boot`), so
the calibrated thresholds are directly comparable with what the
harness produces at run time. It exercises the same production CLI
handlers a verifier runs:

1. Runs the positive baseline across `--baseline-seeds` seeds on
   the in-process plant and pools every per-window `M (dB)`.
2. Runs the power-sag `Ω` battery across `--sag-seeds` seeds and
   records `δ` and `τ_rec` from each run's `sc1_result`.
3. Computes the four thresholds above (`Mmin` is the 5th
   percentile of the pooled baseline `M`, floored at `1 dB`).
4. Recomputes a representative baseline `L_ex` directly (the one
   quantity the harness does not export) to express `Mmin` as the
   additive margin `σ`.
5. Writes the calibrated profile to `configs/profile_rstar.yml`
   and an R0-vs-R\* comparison (CSV + figure) plus a JSON summary
   with full provenance.

## Outputs

- `configs/profile_rstar.yml`: a calibrated profile with
  `profile_id: 1`. Use this profile in subsequent runs to
  benefit from the tighter thresholds.
- `artifacts/calibration/rstar_summary.json`: a JSON record
  mapping every input flag to the derived threshold, with the
  raw `δ` and `τ_rec` distributions included for transparency.

Use the calibrated profile like any other:

```bash
make clean-artifacts && \
ldtc run --config configs/profile_rstar.yml
```

The exported indicators will carry `profile_id: 1`, which
verifiers can use to distinguish R0 from R\* artifacts.

## Re-calibrating

You should re-run the calibrator whenever:

- You change `Δt`, the window length, or the estimator method.
- You move from one device or plant to another.
- The baseline distribution of `M` shifts noticeably (for
  example, due to environmental drift over weeks).

Calibration runs the full harness over several seeds, so budget a
few minutes on the in-process plant (six baseline seeds plus six
power-sag seeds at the `R0` run lengths).

## Notes

- The calibration runs on the in-process plant by default with
  `seed_C = [E, T, R]` matching the demo. To calibrate against
  a hardware plant, edit the script to construct a
  [`HardwarePlantAdapter`][ldtc.plant.hw_adapter.HardwarePlantAdapter]
  instead.
- The baseline and `Ω` trials reuse the same estimators used in
  the CLI, including block bootstrap CIs, so the calibrated
  thresholds are directly compatible with what the harness
  produces at run time.
- Estimator options include the linear / VAR-Granger-like path
  and two MI paths (sklearn MI and Kraskov k-NN MI). Optional
  TE / DI plugin hooks are available; if no backend is installed,
  the methods fall back to MI as a conservative proxy.

## See also

- [Definitions](../concepts/definitions.md): formal statements of
  `Mmin`, `ε`, `τ_max`, `σ`.
- [Runs](runs.md): how to actually exercise the new profile.
- [Reporting](reporting.md): how `profile_id` shows up in the
  manifest.
- [`ldtc.attest.indicators.IndicatorConfig`][ldtc.attest.indicators.IndicatorConfig]:
  the `profile_id` field on the wire.
