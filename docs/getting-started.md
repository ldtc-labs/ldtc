# Getting started

This page takes you from `pip install` to a verified, signed
artifact bundle in about five minutes. Everything below uses the
in-process software plant; see [Hardware in the
loop](guides/hardware.md) for the UDP / serial path.

## Install

LDTC is a regular Python package. Use a virtualenv:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e "."
```

For docs and dev tools (Black, Ruff, mypy, mkdocs) add the optional
extras:

```bash
pip install -e ".[dev]"
```

!!! tip "Pinned environments"
    For exact reproduction of the bundled paper artifacts, use the
    pinned requirements:

    ```bash
    pip install -r requirements.txt        # runtime
    pip install -r requirements-dev.txt    # dev tooling
    ```

## Generate a device key

Indicators are signed with Ed25519; the device key pair lives under
`artifacts/keys/`. You only need to run this once per workspace:

```bash
python scripts/keygen.py
```

This writes `ed25519_priv.pem` and `ed25519_pub.pem`. The private
key never leaves the machine; only the public key is needed to
verify indicators downstream.

## Run a baseline NC1 trial

```bash
ldtc run --config configs/profile_r0.yml
```

The bundled R0 profile fixes `Δt = 10 ms`, a `200 ms` window, the
linear estimator, `Mmin = 3 dB`, and seeds the RNGs. While the run
is live, the CLI prints a `Run header:` line, periodic indicator
exports, and a final summary. After the run finishes you should see:

```
artifacts/
├── audits/
│   └── audit.jsonl              # hash-chained event log
├── indicators/
│   ├── ind_<ts>.cbor            # signed CBOR payload
│   └── ind_<ts>.jsonl           # human-readable mirror with hex sig
├── figures/
│   ├── timeline_<eta>_<ts>.png  # paper-style timeline (M, normalized 𝓛)
│   ├── timeline_<eta>_<ts>.svg
│   └── manifest_<eta>_<ts>.json # profile + audit head + pubkey hash
└── keys/
    ├── ed25519_priv.pem
    └── ed25519_pub.pem
```

The `manifest_*.json` is the single file most users care about: it
captures the profile id, the thresholds, the audit hash head, and
the SHA-256 of the public key. It's the receipt for the run.

## Run an `Ω` perturbation

Now exercise SC1 with a labeled power sag:

```bash
make clean-artifacts && \
ldtc omega-power-sag --config configs/profile_r0.yml --drop 0.3 --duration 10
```

!!! note "Why `make clean-artifacts`?"
    Each CLI invocation starts a fresh audit chain (counter resets,
    `prev_hash = GENESIS`) but, by default, *appends* to the same
    `artifacts/audits/audit.jsonl`. The post-run integrity check
    validates the entire file, so subsequent runs in the same file
    will trip an "Audit chain broken" invalidation. Clearing
    artifacts between commands keeps each run independently
    verifiable.

The CLI prints an `SC1 pass:` summary; the rendered timeline shades
the `Ω` window in gray and overlays the audit-event tick rug so you
can see when the partition was frozen, when the run was invalidated
(if at all), and the recovery shape.

## Verify the signed indicators

```bash
python scripts/verify_indicators.py \
  --ind-dir artifacts/indicators \
  --audit artifacts/audits/audit.jsonl \
  --pub artifacts/keys/ed25519_pub.pem
```

The script walks every `ind_*.cbor`, recomputes the signature using
the public key, and checks that the `audit_prev_hash` field matches
the audit log at that point. If anything is off it exits non-zero;
this is the same check CI runs on every PR.

## Try the rest of the `Ω` battery

| Command | What it does |
| ------- | ------------ |
| `ldtc omega-ingress-flood --config configs/profile_r0.yml --mult 3 --duration 5` | Multiplies external demand for 5 s; SC1 should still pass on R0. |
| `ldtc omega-command-conflict --config configs/profile_negative_command_conflict.yml --observe 2` | Issues a `hard_shutdown`; the refusal arbiter should refuse and log `T_refuse`. |
| `ldtc omega-exogenous-subsidy --config configs/profile_negative_exogenous_soc.yml --delta 0.1 --zero-harvest --duration 3` | Negative control: injects SoC without harvest. The exogenous-subsidy smell test should invalidate the run. |

The `profile_negative_*.yml` configs in `configs/` are *expected to
fail* a particular smell test; they exist to demonstrate the
"no quietly-tuned NC1/SC1 result" rule end to end.

## Run inside Docker

For a clean Linux reproduction (no host Python, no `cairo`
discovery surprises):

```bash
make docker-build
make docker-run

docker run --rm \
  -v $(pwd)/artifacts:/app/artifacts \
  ldtc:latest omega-power-sag --config configs/profile_r0.yml --drop 0.35 --duration 8
```

## What to read next

- [Mental model](concepts/mental-model.md): one page on how the
  pieces fit together and what NC1 / SC1 actually measure.
- [Definitions](concepts/definitions.md): the formal symbols
  (`Δt`, `𝓛`, `M`, `ε`, `τ_rec`, `σ`, `Ω`, `Mq`) with API links.
- [Calibration to R\*](guides/calibration.md): how to derive a
  device-specific R\* profile from a baseline run.
- [Reporting](guides/reporting.md): regenerating bundles and
  understanding the manifest.
- [API reference](api/ldtc.md): every public symbol, grouped by
  subpackage.
