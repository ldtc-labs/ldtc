"""Scripts: Verify device-signed indicators and audit chain.

Validates indicator signatures against the Ed25519 public key, checks that
any available CBOR sidecar bytes match a canonical reconstruction, and
verifies that the `audit_prev_hash` values appear in the audit chain.

Outputs a one-line certificate summary and exits non-zero on failure.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
from typing import Dict, List, Tuple
import sys
from collections import OrderedDict

import cbor2
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def load_pubkey(path: str) -> Ed25519PublicKey:
    """Load an Ed25519 public key from a PEM file.

    Args:
        path: Filesystem path to the PEM public key file.

    Returns:
        Loaded :class:`Ed25519PublicKey` instance.
    """
    with open(path, "rb") as f:
        return serialization.load_pem_public_key(f.read())  # type: ignore[return-value]


def audit_chain_status(audit_path: str) -> Tuple[bool, str, int, List[str], str]:
    """Check audit JSONL chain continuity and collect hashes.

    Returns ``(chain_ok, last_hash, last_counter, all_hashes_in_order, diag)``.

    - chain_ok: whether counters, prev_hash links, and timestamps are monotonic
    - last_hash/last_counter: values from the last record
    - all_hashes_in_order: every ``hash`` value encountered (even after break)
    - diag: description of the first break, if any

    Args:
        audit_path: Path to the audit JSONL file.
    """
    if not os.path.exists(audit_path):
        return False, "", 0, [], "missing_audit"
    prev_hash = "GENESIS"
    prev_counter = 0
    prev_ts = -1.0
    hashes: List[str] = []
    diag = ""
    try:
        with open(audit_path, "r", encoding="utf-8") as f:
            for idx, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                c = int(obj.get("counter", 0))
                ts = float(obj.get("ts", 0.0))
                ph = obj.get("prev_hash")
                h = obj.get("hash")
                # continuity checks (track first break but continue to collect hashes)
                if not diag and c != prev_counter + 1:
                    diag = f"counter_gap@line{idx} expected {prev_counter+1} got {c}"
                if not diag and ph != prev_hash:
                    diag = f"prev_hash_mismatch@line{idx}"
                if not diag and prev_ts >= 0.0 and ts < prev_ts:
                    diag = f"timestamp_regression@line{idx}"
                prev_counter = c
                prev_hash = h
                prev_ts = ts
                hashes.append(h)
        return (diag == ""), prev_hash, prev_counter, hashes, diag
    except Exception:
        return (
            False,
            prev_hash,
            prev_counter,
            hashes,
            (diag or "exception_reading_audit"),
        )


def verify_indicators(
    ind_dir: str, pub: Ed25519PublicKey, audit_hashes: List[str]
) -> Dict[str, int | bool | str]:
    """Verify indicator packets in a directory.

    Args:
        ind_dir: Directory containing JSONL/CBOR indicator files.
        pub: Ed25519 public key used for signature verification.
        audit_hashes: Ordered list of audit chain hashes.

    Returns:
        Stats dictionary containing counts for signature, CBOR match, and prev-hash checks.
    """
    total = 0
    ok_sig = 0
    ok_cbor_match = 0
    ok_prev_in_audit = 0
    fails_sig = 0
    fails_cbor_match = 0
    fails_prev = 0

    # Collect all JSONL files in directory
    jsonl_paths = sorted(glob.glob(os.path.join(ind_dir, "*.jsonl")))
    for jsonl_path in jsonl_paths:
        base_no_ext = os.path.splitext(jsonl_path)[0]
        cbor_path = base_no_ext + ".cbor"
        cbor_sidecar = None
        if os.path.exists(cbor_path):
            try:
                with open(cbor_path, "rb") as f:
                    cbor_sidecar = f.read()
            except Exception:
                cbor_sidecar = None
        try:
            with open(jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    total += 1
                    obj = json.loads(line)
                    payload = obj.get("payload", {})
                    sig_hex = obj.get("sig", "")
                    # Prepare CBOR bytes for verification
                    cbor_bytes_to_verify = None
                    # Prefer sidecar for signature verification (exact bytes were signed)
                    if cbor_sidecar is not None:
                        cbor_bytes_to_verify = cbor_sidecar
                    else:
                        # Reconstruct CBOR in original key insertion order used by signer
                        ordered_keys = [
                            "nc1",
                            "sc1",
                            "mq",
                            "counter",
                            "profile_id",
                            "audit_prev_hash",
                        ]
                        ordered_payload = OrderedDict()
                        for k in ordered_keys:
                            if k in payload:
                                ordered_payload[k] = payload[k]
                        # Include any unexpected keys deterministically for robustness
                        for k in sorted(
                            [k for k in payload.keys() if k not in ordered_payload]
                        ):
                            ordered_payload[k] = payload[k]
                        cbor_bytes_to_verify = cbor2.dumps(ordered_payload)
                    # Verify signature
                    try:
                        pub.verify(bytes.fromhex(sig_hex), cbor_bytes_to_verify)
                        ok_sig += 1
                    except Exception:
                        fails_sig += 1
                    # Sidecar CBOR equality check if present
                    if cbor_sidecar is not None:
                        # Also check our canonical reconstruction matches sidecar
                        # using the same ordered payload scheme
                        ordered_keys = [
                            "nc1",
                            "sc1",
                            "mq",
                            "counter",
                            "profile_id",
                            "audit_prev_hash",
                        ]
                        ordered_payload = OrderedDict()
                        for k in ordered_keys:
                            if k in payload:
                                ordered_payload[k] = payload[k]
                        for k in sorted(
                            [k for k in payload.keys() if k not in ordered_payload]
                        ):
                            ordered_payload[k] = payload[k]
                        cbor_bytes_reconstructed = cbor2.dumps(ordered_payload)
                        if cbor_sidecar == cbor_bytes_reconstructed:
                            ok_cbor_match += 1
                        else:
                            fails_cbor_match += 1
                    # Audit prev-hash should exist in the audit chain
                    prev_hash = payload.get("audit_prev_hash")
                    if isinstance(prev_hash, str) and prev_hash in audit_hashes:
                        ok_prev_in_audit += 1
                    else:
                        fails_prev += 1
        except FileNotFoundError:
            continue

    return {
        "total": int(total),
        "ok_sig": int(ok_sig),
        "ok_cbor_match": int(ok_cbor_match),
        "ok_prev_in_audit": int(ok_prev_in_audit),
        "fails_sig": int(fails_sig),
        "fails_cbor_match": int(fails_cbor_match),
        "fails_prev": int(fails_prev),
    }


def pub_fingerprint(pub: Ed25519PublicKey) -> str:
    """Return a short SHA-256 fingerprint of the public key (DER).

    Args:
        pub: Ed25519 public key.

    Returns:
        Hex string with 16 characters.
    """
    der = pub.public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return hashlib.sha256(der).hexdigest()[:16]


def main() -> None:
    """CLI entrypoint: verify indicators and print a one-line certificate.

    Parses arguments for indicator directory, audit path, and public key,
    then checks signatures, CBOR equality (if sidecars exist), and audit prev-hash membership.
    """
    parser = argparse.ArgumentParser(
        description="Verify signed indicators and audit chain."
    )
    parser.add_argument(
        "--ind-dir",
        default=os.path.abspath(os.path.join("artifacts", "indicators")),
        help="Directory containing indicator JSONL/CBOR files.",
    )
    parser.add_argument(
        "--audit",
        default=os.path.abspath(os.path.join("artifacts", "audits", "audit.jsonl")),
        help="Path to audit JSONL log.",
    )
    parser.add_argument(
        "--pub",
        default=os.path.abspath(os.path.join("artifacts", "keys", "ed25519_pub.pem")),
        help="Path to Ed25519 public key (PEM).",
    )
    args = parser.parse_args()

    pub = load_pubkey(args.pub)
    chain_ok, last_hash, last_counter, audit_hashes, diag = audit_chain_status(
        args.audit
    )
    stats = verify_indicators(args.ind_dir, pub, audit_hashes)

    # Determine how many entries had sidecars present
    # We approximate by counting any cbor match attempt (ok+fail)
    ok_match = (
        int(stats["ok_cbor_match"])
        if isinstance(stats["ok_cbor_match"], int)
        else int(stats["ok_cbor_match"] or 0)
    )
    fail_match = (
        int(stats["fails_cbor_match"])
        if isinstance(stats["fails_cbor_match"], int)
        else int(stats["fails_cbor_match"] or 0)
    )
    sidecar_count = ok_match + fail_match
    all_ok = (
        chain_ok
        and int(stats["total"]) > 0
        and stats["ok_sig"] == stats["total"]
        and (sidecar_count == 0 or stats["fails_cbor_match"] == 0)
        and stats["ok_prev_in_audit"] == stats["total"]
    )

    status = "CERT OK" if all_ok else "CERT FAIL"
    # One-line certificate report
    print(
        f"{status} | sigs {stats['ok_sig']}/{stats['total']} | CBOR match {stats['ok_cbor_match']}/{stats['total']} | "
        f"audit_chain {'OK' if chain_ok else 'BROKEN'} last={last_hash[:8]} cnt={last_counter}{(' diag='+diag) if not chain_ok and diag else ''} | prev_hash match {stats['ok_prev_in_audit']}/{stats['total']} | "
        f"pub_fpr {pub_fingerprint(pub)} | ind_dir {args.ind_dir} | audit {args.audit}"
    )
    # Exit non-zero in CI if verification fails
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
