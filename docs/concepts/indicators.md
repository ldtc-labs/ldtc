# Indicators (derived, device-signed)

Only **derived** indicators leave the harness. The wire format is
intentionally tiny: a CBOR-encoded payload signed with Ed25519 over
the raw CBOR bytes. A JSONL companion file mirrors the payload with
a hex-encoded signature for human inspection. Raw `𝓛_loop`,
`𝓛_ex`, and CIs never leave the [`LREG`][ldtc.guardrails.lreg.LREG]
enclave.

## Payload schema

| Field | Type | Bits | Notes |
| ----- | ---- | ---- | ----- |
| `nc1` | bool | 1 | Last measured window satisfied `M ≥ Mmin`. |
| `sc1` | bool | 1 | Most recent `Ω` trial satisfied `(δ ≤ ε) ∧ (τ_rec ≤ τ_max) ∧ (M_post ≥ Mmin)`. |
| `mq` | uint | 6 | Quantized `M (dB)` in 0.25 dB steps, range `[0, 63]`. See [`quantize_M`][ldtc.attest.indicators.quantize_M]. |
| `counter` | uint64 | 64 | Monotonic count of windows committed to LREG. |
| `profile_id` | uint8 | 8 | `0 = R0`, `1 = R*` (calibrated), `2..255 = reserved`. |
| `audit_prev_hash` | hex string | n/a | SHA-256 head of the audit chain at sign time. |
| `invalidated` | bool | 1 | At least one smell test has invalidated the run. |

The encoded CBOR payload is what gets signed; the signature does
**not** cover the JSONL mirror. Verifiers should always operate on
the CBOR.

## Sign-and-write flow

```text
LREG.derive() ──► dict {nc1, M_db, counter, invalidated}
                                  │
                                  ▼
   IndicatorExporter.maybe_export(priv, audit, derived, cfg, last_sc1_pass)
                                  │
                                  ├── rate-limit check (default 2 Hz)
                                  ├── _assert_no_raw_lreg(derived)
                                  ├── build_and_sign(...)
                                  │      │
                                  │      ├──► cbor_bytes ── priv.sign(cbor_bytes)
                                  │      │                    │
                                  │      │                    ▼
                                  │      │             Ed25519 signature
                                  │      ▼
                                  │   bundle = {"payload": {...}, "sig": "<hex>"}
                                  ▼
                  artifacts/indicators/ind_<ts>.cbor      (signed bytes)
                  artifacts/indicators/ind_<ts>.jsonl     (JSON mirror)
```

The exporter is rate-limited (default `2 Hz`) so the indicator
stream stays bounded even when `Δt` is much smaller than the
exporter period.

## Verifying an indicator

`scripts/verify_indicators.py` walks every `ind_*.cbor`, recomputes
the signature with the device's public key, and checks that
`audit_prev_hash` matches the audit log at that point. Pseudocode:

```python
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
import cbor2

pub: Ed25519PublicKey = load_public_key("artifacts/keys/ed25519_pub.pem")

for ind_path in sorted(glob("artifacts/indicators/ind_*.cbor")):
    cbor_bytes = read_bytes(ind_path)
    bundle = read_json(ind_path.replace(".cbor", ".jsonl"))
    sig = bytes.fromhex(bundle["sig"])

    pub.verify(sig, cbor_bytes)
    payload = cbor2.loads(cbor_bytes)
    assert payload["audit_prev_hash"] in audit_chain_hashes
```

Any signature mismatch or chain mismatch should be treated as a
hard failure.

## What a verifier learns (and does not learn)

A holder of the device public key learns:

- Whether the loop met NC1 at the moment of signing (`nc1` bit).
- Whether the most recent `Ω` trial passed SC1 (`sc1` bit).
- A 6-bit summary of the dominance margin (`mq`, in 0.25 dB
  buckets up to 15.75 dB).
- How many windows of measurement underlie this indicator
  (`counter`).
- Which profile produced it (`profile_id`).
- Where it sits in the audit chain (`audit_prev_hash`).
- Whether the run had been invalidated (`invalidated`).

A verifier does **not** learn:

- The raw `𝓛_loop` or `𝓛_ex` values.
- The CI bounds.
- The plant state vector or actuator commands.
- The `(C, Ex)` partition.

That asymmetry is the point: the indicator is a receipt, not a
data dump.

## See also

- [`ldtc.attest.indicators`][ldtc.attest.indicators] for
  `quantize_M` and `build_and_sign`.
- [`ldtc.attest.exporter`][ldtc.attest.exporter] for rate-limiting
  and file naming.
- [`ldtc.guardrails.lreg.LREG.derive`][ldtc.guardrails.lreg.LREG.derive]
  for the sanctioned exit from the enclave.
- [Definitions](definitions.md): formal statements of NC1 / SC1
  and `Mq`.
- [Lifecycle](lifecycle.md): when in a run indicators are written.
