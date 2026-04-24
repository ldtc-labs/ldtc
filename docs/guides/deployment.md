# Deployment

LDTC is designed to run as a single, long-lived process on the
machine that owns the device under test. Almost all "deployment"
choices reduce to: where do `artifacts/` and `configs/` live, who
holds the device key, and how is the process supervised?

This page covers four common shapes:

1. Local one-shot run.
2. Docker container with a host-mounted artifacts volume.
3. Long-running operator daemon under `systemd`.
4. CI pipeline producing signed verification bundles.

## 1. Local one-shot run

Use this for ad-hoc verification on your workstation.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python scripts/keygen.py
make clean-artifacts && ldtc run --config configs/profile_r0.yml
python scripts/verify_indicators.py \
  --ind-dir artifacts/indicators \
  --audit artifacts/audits/audit.jsonl \
  --pub artifacts/keys/ed25519_pub.pem
```

This is exactly the [Getting Started](../getting-started.md)
flow.

## 2. Docker

The bundled `Dockerfile` is a small `python:3.11-slim` image that
copies the package, installs runtime deps, and sets `ldtc` as the
entrypoint. Build it once:

```bash
make docker-build
```

Run a baseline with the host's `artifacts/` directory mapped in
so audits and indicators persist:

```bash
make docker-run
# equivalent to:
docker run --rm \
  -v $(pwd)/artifacts:/app/artifacts \
  ldtc:latest run --config configs/profile_r0.yml
```

Run any other CLI subcommand the same way:

```bash
docker run --rm \
  -v $(pwd)/artifacts:/app/artifacts \
  ldtc:latest omega-power-sag --config configs/profile_r0.yml --drop 0.35 --duration 8
```

!!! tip "Key handling in containers"
    Generate the key pair on the host (`python scripts/keygen.py`)
    and let the container read it through the mounted
    `artifacts/keys/` directory. Avoid baking private keys into
    the image.

## 3. Long-running operator daemon (systemd)

For an unattended operator setup (for example, a hardware-in-the-
loop rig that runs continuous baseline + nightly `Ω` battery), wrap
`ldtc` in a `systemd` unit:

```ini
# /etc/systemd/system/ldtc-baseline.service
[Unit]
Description=LDTC baseline verification loop
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/ldtc
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/ldtc/.venv/bin/ldtc run --config configs/profile_rstar.yml
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Pair it with a `timer` for nightly `Ω` trials:

```ini
# /etc/systemd/system/ldtc-omega.timer
[Unit]
Description=Nightly LDTC Ω battery

[Timer]
OnCalendar=*-*-* 02:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

```ini
# /etc/systemd/system/ldtc-omega.service
[Unit]
Description=LDTC Ω battery (one-shot)

[Service]
Type=oneshot
WorkingDirectory=/opt/ldtc
Environment=PYTHONUNBUFFERED=1
ExecStartPre=/opt/ldtc/.venv/bin/python -m ldtc.cli.main omega-power-sag --config configs/profile_rstar.yml --drop 0.3 --duration 10
ExecStart=/opt/ldtc/.venv/bin/python -m ldtc.cli.main omega-ingress-flood --config configs/profile_rstar.yml --mult 3 --duration 5
```

Two common operational concerns:

- **Audit rotation.** The default audit log appends forever.
  Either rotate it (move the file aside between runs and let
  `ldtc` recreate it) or set up a cron job that ships completed
  audits to long-term storage.
- **Disk usage of indicators.** At 2 Hz, indicators add roughly
  150 bytes / second of CBOR plus the JSONL mirror. For a
  sustained operator run, prune older `ind_*` files after
  shipping them to a verifier.

## 4. CI pipeline

Use the harness inside CI to gate releases on a passing baseline.
The shipped `.github/workflows/ci.yml` does roughly this:

```yaml
- name: Install
  run: |
    python -m pip install --upgrade pip
    pip install -e .[dev]

- name: Lint, type-check, test
  run: |
    ruff check .
    mypy src tests scripts
    pytest -q

- name: Build verification artifact bundle
  run: |
    python scripts/keygen.py
    ldtc run --config configs/profile_r0.yml
    ldtc omega-power-sag --config configs/profile_r0.yml --drop 0.3 --duration 5

- name: Verify signed indicators
  run: |
    python scripts/verify_indicators.py \
      --ind-dir artifacts/indicators \
      --audit artifacts/audits/audit.jsonl \
      --pub artifacts/keys/ed25519_pub.pem

- name: Upload artifacts
  uses: actions/upload-artifact@v4
  with:
    name: ldtc-artifacts
    path: artifacts/
```

Two notes for CI:

- Each job needs to either generate fresh keys (test only) or
  fetch the device's real key from a secrets store. Do not
  commit `ed25519_priv.pem`.
- The `mkdocs build --strict` job in
  `.github/workflows/docs.yml` runs on every PR so doc
  regressions are caught early.

## Choosing a profile

| Setting | When to use |
| ------- | ----------- |
| `configs/profile_r0.yml` | Default; demos, smoke tests, CI. |
| `configs/profile_rstar.yml` | Real device or specific synthetic plant; produced by `scripts/calibrate_rstar.py` (see [Calibration](calibration.md)). |
| `configs/profile_negative_*.yml` | Negative controls; expected to invalidate a particular smell test. Useful for end-to-end CI confirmation that the guards still bite. |

## See also

- [Hardware in the loop](hardware.md): wiring a real device into
  the same `ldtc` subcommands.
- [Calibration](calibration.md): producing the per-device R\*
  profile referenced by these deployments.
- [Reporting](reporting.md): the bundle each run produces, which
  is the file you actually ship to a verifier.
- [Troubleshooting](../meta/troubleshooting.md): common failure
  modes when running unattended.
