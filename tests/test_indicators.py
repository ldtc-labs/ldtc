from __future__ import annotations

import json

from ldtc.attest.indicators import quantize_M, IndicatorConfig, build_and_sign
from ldtc.attest.keys import ensure_keys, KeyPaths
from ldtc.guardrails.audit import AuditLog
from scripts.verify_indicators import verify_indicators, audit_chain_status


def test_quantize_M_step_and_rounding():
    # exact quarter-dB steps
    assert quantize_M(0.00) == 0
    assert quantize_M(0.25) == 1
    assert quantize_M(0.50) == 2
    assert quantize_M(3.00) == 12
    assert quantize_M(7.50) == 30
    # rounding to nearest quarter (bankers rounding only on .5 of step; avoid ties)
    assert quantize_M(0.24) == 1  # 0.24/0.25 ~= 0.96 → rounds to 1
    assert quantize_M(0.13) == 1  # 0.13/0.25 ~= 0.52 → rounds to 1
    assert quantize_M(0.12) == 0  # 0.12/0.25 ~= 0.48 → rounds to 0


def test_quantize_M_clamp_and_saturation():
    # negative clamps to 0
    assert quantize_M(-10.0) == 0
    # upper saturation at 63 (15.75 dB)
    assert quantize_M(15.75) == 63
    assert quantize_M(16.00) == 63
    assert quantize_M(100.00) == 63


def test_quantize_M_monotonic_over_range():
    last = -1
    for m in [x * 0.1 for x in range(-50, 250)]:  # -5.0 dB .. 25.0 dB
        q = quantize_M(m)
        assert q >= last
        last = q


def test_build_and_sign_includes_mq(tmp_path):
    # keys and audit
    kp = KeyPaths(str(tmp_path / "k_priv.pem"), str(tmp_path / "k_pub.pem"))
    priv, _pub = ensure_keys(kp)
    audit = AuditLog(str(tmp_path / "audit.jsonl"))
    audit.append("start", {})
    # build with a known M_db
    M_db = 3.5
    cbor_bytes, bundle = build_and_sign(
        priv,
        audit,
        {"nc1": True, "M_db": M_db, "counter": 42},
        IndicatorConfig(),
        last_sc1_pass=True,
    )
    assert isinstance(cbor_bytes, (bytes, bytearray))
    assert "payload" in bundle and "sig" in bundle
    payload = bundle["payload"]
    assert payload["nc1"] is True
    assert payload["sc1"] is True
    # mq is the quantized M_db per 0.25 dB step and 6-bit saturation
    assert payload["mq"] == quantize_M(M_db)
    assert 0 <= payload["mq"] <= 63


def test_indicator_signature_verification_tool(tmp_path):
    # Prepare keys
    kp = KeyPaths(str(tmp_path / "k_priv.pem"), str(tmp_path / "k_pub.pem"))
    priv, pub = ensure_keys(kp)
    # Prepare audit and one indicator payload
    audit_path = tmp_path / "audit.jsonl"
    ind_dir = tmp_path / "ind"
    ind_dir.mkdir()
    audit = AuditLog(str(audit_path))
    audit.append("start", {})
    cbor_bytes, bundle = build_and_sign(
        priv,
        audit,
        {"nc1": True, "M_db": 3.25, "counter": audit.counter},
        IndicatorConfig(),
        last_sc1_pass=True,
    )
    # Write indicator JSONL and CBOR sidecar
    ind_path = ind_dir / "ind_0001.jsonl"
    with open(ind_path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"payload": bundle["payload"], "sig": bundle["sig"]}) + "\n")
    sidecar_path = ind_dir / "ind_0001.cbor"
    with open(sidecar_path, "wb") as f:
        f.write(cbor_bytes)
    # Verify
    chain_ok, last_hash, last_counter, audit_hashes, diag = audit_chain_status(
        str(audit_path)
    )
    assert chain_ok is True and last_counter == 1
    stats = verify_indicators(str(ind_dir), pub, audit_hashes)
    assert stats["total"] == 1
    assert stats["ok_sig"] == 1
    assert stats["ok_cbor_match"] == 1
    assert stats["ok_prev_in_audit"] == 1
