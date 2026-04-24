"""Attestation and indicator export.

`attest` is the boundary that everything inside the LDTC harness has to
cross before leaving the machine. It manages the device's Ed25519 key
pair, encodes the derived NC1/SC1 indicators into a compact payload,
signs that payload, and emits the signed bundle to disk under a strict
rate limit:

- [`keys`][ldtc.attest.keys] loads or generates Ed25519 keys stored as
  PEM.
- [`indicators`][ldtc.attest.indicators] defines the indicator payload
  schema, `M (dB)` quantization, and CBOR signing.
- [`exporter`][ldtc.attest.exporter] is the rate-limited writer for
  JSONL + CBOR artifacts; it enforces the no-raw-LREG export policy.

The exporter is intentionally paranoid about the no-raw-LREG rule: it
walks the payload before signing and the bundle after signing, refusing
to emit anything that contains `L_loop`, `L_ex`, `ci_loop`, or `ci_ex`.
That keeps the device-signed artifact safe to publish and verify
independently.
"""
