# Calibration to R\*

The bundled `R0` profile uses generic thresholds (`Mmin = 3 dB`,
`ε = 0.15`, `τ_max = 60 s`). For a real device, you almost
certainly want **R\***: the same harness, but with thresholds
calibrated from a quiet baseline and a power-sag battery on the
actual hardware (or your specific synthetic plant). This is the
process the manuscript Methods §8.6 describes.

## What gets calibrated

| Threshold | Meaning | Calibration rule |
| --------- | ------- | ---------------- |
| `Mmin (dB)` | NC1 acceptance margin. | One-sided 95% lower bound of `M (dB)` over the quiescent baseline, floored at `1 dB`. |
| `ε` | SC1 dip tolerance. | 90th percentile of `δ` across `Ω` trials plus a small safety margin, capped at `0.25`. |
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
  --dt 0.01 \
  --window-sec 0.25 \
  --method linear \
  --baseline-sec 15 \
  --omega-trials 6 \
  --sag-drop 0.3 \
  --sag-duration 8 \
  --out configs/profile_rstar.yml \
  --summary artifacts/calibration/rstar_summary.json
```

The script:

1. Spins up the in-process plant and runs a quiescent baseline
   for `--baseline-sec` seconds at the requested `Δt`.
2. Runs `--omega-trials` power-sag trials and records `δ` and
   `τ_rec` for each.
3. Computes the four thresholds above.
4. Writes them into a fresh profile YAML at `--out`.
5. Writes a JSON summary at `--summary` containing the inputs and
   the derived thresholds (for the paper supplement).

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

Calibration is cheap: a 15 s baseline plus six 8 s power-sag
trials is well under a minute on the in-process plant.

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
