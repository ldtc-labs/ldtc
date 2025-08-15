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
    """
    Defense-in-depth: reject any payload containing raw LREG fields.
    Recurses through dicts/lists/tuples.
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
    """
    Rate-limited export of device-signed indicator packets to JSONL and CBOR.
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
