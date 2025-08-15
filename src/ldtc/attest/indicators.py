from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

import cbor2
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ..guardrails.audit import AuditLog


@dataclass
class IndicatorConfig:
    Mmin_db: float = 3.0
    profile_id: int = 0  # 0=R0, 1=R*


def quantize_M(M_db: float) -> int:
    # 0..15.75 dB in 0.25 steps -> 0..63
    q = int(max(0.0, min(63.0, round(M_db / 0.25))))
    return q


def build_and_sign(
    priv: Ed25519PrivateKey,
    audit: AuditLog,
    derived: Dict[str, float | int | bool],
    cfg: IndicatorConfig,
    last_sc1_pass: bool,
) -> Tuple[bytes, Dict]:
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
