# Reporting & Figures

## Verification Timeline

After a run, render the verification timeline figure bundle:

```bash
python -c "from ldtc.reporting.artifacts import bundle; print(bundle('artifacts/figures','artifacts/audits/audit.jsonl',[{'eta':'power_sag','delta':0.1,'tau_rec':5.0,'pass':True}]))"
```

Outputs:

- `artifacts/figures/verification_timeline.png`
- `artifacts/figures/sc1_table.csv`

## Extending the Plot

To include `M(dB)` traces, log per-window `M` into the audit or a sidecar CSV and modify `reporting/timeline.py` to plot it alongside the audit density.
