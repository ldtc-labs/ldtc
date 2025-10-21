# Getting Started

## Install

```bash
python -m pip install --upgrade pip
pip install -e "."
# Optional: docs/dev tools
pip install -e ".[dev]"
```

## Quick run

Baseline NC1 run with defaults:

```bash
ldtc run --config configs/profile_r0.yml
```

Run Ω power-sag and generate figures:

```bash
ldtc omega-power-sag --config configs/profile_r0.yml --drop 0.3 --duration 10
```

Artifacts are written under `artifacts/` (audit, indicators, figures).

## Project layout

See `CONTRIBUTING.md` for a high-level map and development workflow.
