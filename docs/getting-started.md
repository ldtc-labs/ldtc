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

## Pinned environments

For exact reproduction of included artifacts/figures:

```bash
# Runtime (reproduce artifacts/figures)
pip install -r requirements.txt

# Dev tooling (tests, lint, typing, notebooks)
pip install -r requirements-dev.txt
```

## Keys (device-signed indicators)

Indicators are signed with Ed25519. Generate keys once per workspace:

```bash
python scripts/keygen.py  # writes artifacts/keys/ed25519_{pub,priv}.pem
```

Verify indicators in CI or locally:

```bash
python scripts/verify_indicators.py \
  --ind-dir artifacts/indicators \
  --audit artifacts/audits/audit.jsonl \
  --pub artifacts/keys/ed25519_pub.pem
```

## Docker (clean Linux repro)

```bash
# Build the image
make docker-build

# Run baseline NC1 loop inside the container (artifacts mapped to host)
make docker-run

# Or run any CLI subcommand, e.g., an Ω power-sag trial
docker run --rm \
  -v $(pwd)/artifacts:/app/artifacts \
  ldtc:latest omega-power-sag --config configs/profile_r0.yml --drop 0.35 --duration 8
```

## Project layout

See `CONTRIBUTING.md` for a high-level map and development workflow.
