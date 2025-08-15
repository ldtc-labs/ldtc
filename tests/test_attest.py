from __future__ import annotations

from ldtc.attest.keys import ensure_keys, KeyPaths
from ldtc.guardrails.audit import AuditLog
from ldtc.attest.indicators import IndicatorConfig, build_and_sign


def test_build_and_sign(tmp_path):
    kp = KeyPaths(str(tmp_path / "k_priv.pem"), str(tmp_path / "k_pub.pem"))
    priv, pub = ensure_keys(kp)
    audit = AuditLog(str(tmp_path / "audit.jsonl"))
    audit.append("start", {})
    payload_cbor, bundle = build_and_sign(
        priv, audit, {"nc1": True, "M_db": 3.5, "counter": 10}, IndicatorConfig(), True
    )
    assert bundle["payload"]["sc1"] is True
    assert isinstance(payload_cbor, (bytes, bytearray))
    assert "sig" in bundle
