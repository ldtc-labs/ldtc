"""Indicator encoding and signing.

Defines the indicator payload schema, `M (dB)` quantization, and the
Ed25519 signing step that produces a CBOR-encoded, device-signed packet.

The payload is intentionally small: NC1 / SC1 booleans, a 6-bit `Mq`
code, the run counter, the active profile id, the audit chain head, and
an `invalidated` flag. That gives auditors enough to verify a result
without exposing any raw `𝓛` value.

See Also:
    `paper/main.tex`: Methods: Measurement and Attestation; Exported
    indicators.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

import cbor2
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ..guardrails.audit import AuditLog


@dataclass
class IndicatorConfig:
    """Configuration for indicator encoding.

    Attributes:
        Mmin_db: Threshold for NC1 pass, in dB.
        profile_id: Profile selector (`0 = R0`, `1 = R*`).
    """

    Mmin_db: float = 3.0
    profile_id: int = 0  # 0=R0, 1=R*


def quantize_M(M_db: float) -> int:
    """Quantize loop-dominance `M (dB)` to a 6-bit code.

    Maps `M_db` linearly onto the integer range `[0, 63]` with a 0.25 dB
    step, so the encoded `Mq` covers `0` through `15.75` dB. Values
    outside the range are clamped.

    Args:
        M_db: Decibel loop-dominance value.

    Returns:
        Integer in the range `[0, 63]` using 0.25 dB steps.
    """
    q = int(max(0.0, min(63.0, round(M_db / 0.25))))
    return q


def build_and_sign(
    priv: Ed25519PrivateKey,
    audit: AuditLog,
    derived: Dict[str, float | int | bool],
    cfg: IndicatorConfig,
    last_sc1_pass: bool,
) -> Tuple[bytes, Dict]:
    """Build CBOR indicator payload and Ed25519 signature bundle.

    The returned `cbor_bytes` is what gets signed and persisted; the
    `bundle_dict` is the JSON-friendly view (`{"payload": ..., "sig":
    "<hex>"}`) used by the JSONL artifact.

    Args:
        priv: Ed25519 private key (typically from
            [`ensure_keys`][ldtc.attest.keys.ensure_keys]).
        audit: Audit log providing the last hash head, anchoring this
            indicator to the run's audit chain.
        derived: Derived indicators from
            [`LREG.derive`][ldtc.guardrails.lreg.LREG.derive] (must not
            contain raw `𝓛` fields).
        cfg: Indicator configuration with profile id and thresholds.
        last_sc1_pass: Whether SC1 passed in the most recent evaluation.

    Returns:
        Tuple `(cbor_bytes, bundle_dict)` where `bundle_dict["sig"]` is
        the hex-encoded Ed25519 signature over `cbor_bytes`.
    """
    payload = {
        "nc1": bool(derived.get("nc1", False)),
        "sc1": bool(last_sc1_pass),
        "mq": quantize_M(float(derived.get("M_db", 0.0))),
        "counter": int(derived.get("counter", 0)),
        "profile_id": cfg.profile_id,
        "audit_prev_hash": audit.last_hash,
        "invalidated": bool(derived.get("invalidated", False)),
    }
    # CBOR-encode then sign
    cbor = cbor2.dumps(payload)
    sig = priv.sign(cbor)
    bundle = {"payload": payload, "sig": sig.hex()}
    return cbor, bundle
