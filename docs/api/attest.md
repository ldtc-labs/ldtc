# ldtc.attest

Device-signed indicator generation, encoding, and persistence.
This is the only sanctioned way for run results to leave the
machine; every byte that escapes lives in a CBOR payload signed
with Ed25519.

| Module | Headline symbols | Use it for |
| ------ | ---------------- | ---------- |
| [`indicators`](#indicators) | [`IndicatorConfig`][ldtc.attest.indicators.IndicatorConfig], [`quantize_M`][ldtc.attest.indicators.quantize_M], [`build_and_sign`][ldtc.attest.indicators.build_and_sign] | Turn `LREG.derive(...)` plus the latest SC1 decision into a signed CBOR payload. |
| [`exporter`](#exporter) | [`IndicatorExporter`][ldtc.attest.exporter.IndicatorExporter] | Rate-limited writer for `ind_*.cbor` and the JSONL companion. |
| [`keys`](#keys) | [`KeyPaths`][ldtc.attest.keys.KeyPaths], [`ensure_keys`][ldtc.attest.keys.ensure_keys] | Load or generate an Ed25519 key pair under `artifacts/keys/`. |

See [Indicators](../concepts/indicators.md) for the wire format
and verifier walkthrough.

::: ldtc.attest
    options:
      members: false
      show_root_heading: false
      show_source: false

## indicators

::: ldtc.attest.indicators

## exporter

::: ldtc.attest.exporter

## keys

::: ldtc.attest.keys
