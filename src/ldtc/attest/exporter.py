"""Attest: Indicator exporter.

Rate-limited writer for device-signed indicator bundles in JSONL and CBOR,
with strict enforcement of the no-raw-LREG export policy.

See Also:
    paper/main.tex — Methods: Measurement & Attestation; Export policy.
"""

from __future__ import annotations

import json
import os
import time
from typing import Dict, Tuple, Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .indicators import IndicatorConfig, build_and_sign
from ..guardrails.audit import AuditLog


_BANNED_RAW_KEYS = {"L_loop", "L_ex", "ci_loop", "ci_ex"}


def _assert_no_raw_lreg(obj: Any) -> None:
    """Defense-in-depth: reject any payload containing raw LREG fields.

    Recurses through dicts/lists/tuples and raises ``ValueError`` if any
    forbidden key is encountered.
    """
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            if any(k in _BANNED_RAW_KEYS for k in cur.keys()):
                raise ValueError(
                    "raw LREG export blocked by policy (banned keys present)"
                )
            stack.extend(cur.values())
        elif isinstance(cur, (list, tuple)):
            stack.extend(cur)
        # primitives are ignored


class IndicatorExporter:
    """Rate-limited export of device-signed indicator packets.

    Writes JSONL and CBOR artifacts side-by-side after signing a derived
    indicator payload. Enforces the no-raw-LREG policy.

    Args:
        out_dir: Output directory for indicator artifacts.
        rate_hz: Maximum export rate in Hz.
    """

    def __init__(self, out_dir: str, rate_hz: float = 2.0) -> None:
        self.out_dir = out_dir
        self.min_interval = 1.0 / max(0.1, rate_hz)
        os.makedirs(self.out_dir, exist_ok=True)
        self._last = 0.0

    def maybe_export(
        self,
        priv: Ed25519PrivateKey,
        audit: AuditLog,
        derived: Dict[str, float | int | bool],
        cfg: IndicatorConfig,
        last_sc1_pass: bool,
    ) -> Tuple[bool, str]:
        """Export a signed indicator bundle if rate limit allows.

        Args:
            priv: Ed25519 private key.
            audit: Audit log instance (provides last hash head).
            derived: Derived indicators from LREG (no raw L fields).
            cfg: Indicator configuration including profile id.
            last_sc1_pass: Whether SC1 passed in the last evaluation.

        Returns:
            Tuple ``(exported, base_path)`` where ``base_path`` is the file path
            prefix for generated artifacts.
        """
        now = time.time()
        if now - self._last < self.min_interval:
            return False, ""
        self._last = now
        # Guard: ensure no raw LREG fields are present in derived payload
        _assert_no_raw_lreg(derived)
        cbor, bundle = build_and_sign(priv, audit, derived, cfg, last_sc1_pass)
        # Guard: ensure nothing slipped into the signed bundle either
        _assert_no_raw_lreg(bundle)
        # write side-by-side
        base = os.path.join(self.out_dir, f"ind_{int(now*1000)}")
        with open(base + ".jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(bundle, sort_keys=True) + "\n")
        with open(base + ".cbor", "wb") as f:
            f.write(cbor)
        return True, base
