# Minimal run example

The smallest possible end-to-end run uses
`examples/minimal_run.py`, which is a thin wrapper around the
default R0 profile:

```python
import os
import subprocess
import sys


def main():
    cfg = os.path.join("configs", "profile_r0.yml")
    subprocess.run(
        [sys.executable, "-m", "ldtc.cli.main", "run", "--config", cfg],
        check=True,
    )


if __name__ == "__main__":
    main()
```

Run it from a clean workspace:

```bash
make clean-artifacts && python examples/minimal_run.py
```

This is exactly equivalent to:

```bash
make clean-artifacts && ldtc run --config configs/profile_r0.yml
```

## What you should see

After about 10 seconds, the `artifacts/` tree will look like:

```text
artifacts/
├── audits/audit.jsonl
├── indicators/
│   ├── ind_<ts>.cbor
│   └── ind_<ts>.jsonl
├── figures/
│   ├── timeline_baseline_<ts>.png
│   ├── timeline_baseline_<ts>.svg
│   └── manifest_baseline_<ts>.json
└── keys/
    ├── ed25519_priv.pem
    └── ed25519_pub.pem
```

A peek at one indicator:

```bash
jq . artifacts/indicators/ind_*.jsonl | head
```

```json
{
  "payload": {
    "audit_prev_hash": "<hex>",
    "counter": 42,
    "invalidated": false,
    "mq": 14,
    "nc1": true,
    "profile_id": 0,
    "sc1": true
  },
  "sig": "<hex>"
}
```

## Verify the run

```bash
python scripts/verify_indicators.py \
  --ind-dir artifacts/indicators \
  --audit artifacts/audits/audit.jsonl \
  --pub artifacts/keys/ed25519_pub.pem
```

The script walks every `ind_*.cbor`, recomputes the Ed25519
signature with the public key, and checks that
`audit_prev_hash` matches the audit log at that point.

## See also

- [Notebooks](notebooks.md): the same flow visualized in Jupyter.
- [Runs](../guides/runs.md): every CLI subcommand and the
  expected outputs.
- [Lifecycle](../concepts/lifecycle.md): what happened during
  those 10 seconds.
