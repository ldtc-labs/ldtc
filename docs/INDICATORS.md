# Indicators (Derived, Device-Signed)

Only **derived indicators** are exported:

| Field           | Type  | Notes                                             |
|----------------|-------|---------------------------------------------------|
| `nc1`          | 1 bit | Last measured window satisfied `M ≥ Mmin`         |
| `sc1`          | 1 bit | Most recent Ω trial passed SC1                    |
| `mq`           | 6 bit | Quantized `M(dB)` in 0.25 dB steps (0..63)        |
| `counter`      | u64   | Monotonic count of windows written to LREG        |
| `profile_id`   | u8    | 0=R0, 1=R* (calibrated), 2+=reserved               |
| `audit_prev_hash` | str | SHA-256 of previous audit record (tamper-evidence) |

Serialization: **CBOR** payload signed with **Ed25519**. A JSONL companion file mirrors the payload with hex signature for inspection.

Signature covers: `CBOR(payload)` (the raw CBOR bytes), not the JSONL.

**Note:** raw `L_loop`, `L_ex`, and CIs never leave LREG.
