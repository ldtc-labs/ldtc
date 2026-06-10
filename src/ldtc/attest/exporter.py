"""Indicator exporter.

Rate-limited writer for device-signed indicator bundles. Each call to
[`IndicatorExporter.maybe_export`][ldtc.attest.exporter.IndicatorExporter.maybe_export]
either:

1. Emits a paired `*.jsonl` and `*.cbor` artifact for the current
   window, or
2. Returns `(False, "")` because the configured rate limit has not
   elapsed yet.

A defense-in-depth scan rejects payloads or bundles containing raw
`𝓛` fields (`L_loop`, `L_ex`, `ci_loop`, `ci_ex`).

See Also:
    `paper/main.tex`: Methods: Measurement and Attestation; Export
    policy.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Tuple

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ..guardrails.audit import AuditLog
from .indicators import IndicatorConfig, build_and_sign

_BANNED_RAW_KEYS = {"L_loop", "L_ex", "ci_loop", "ci_ex"}


def _assert_no_raw_lreg(obj: Any) -> None:
    """Defense-in-depth: reject any payload containing raw LREG fields.

    Walks dicts, lists, and tuples iteratively and raises
    [`ValueError`][] if any forbidden key is encountered. Primitives are
    ignored.

    Args:
        obj: Arbitrary JSON-like structure to scan.

    Raises:
        ValueError: If any banned LREG key (`L_loop`, `L_ex`, `ci_loop`,
            `ci_ex`) is present anywhere in the structure.
    """
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            if any(k in _BANNED_RAW_KEYS for k in cur.keys()):
                raise ValueError("raw LREG export blocked by policy (banned keys present)")
            stack.extend(cur.values())
        elif isinstance(cur, (list, tuple)):
            stack.extend(cur)
        # primitives are ignored


class IndicatorExporter:
    """Rate-limited export of device-signed indicator packets.

    Writes JSONL and CBOR artifacts side-by-side after signing a derived
    indicator payload. Enforces the no-raw-LREG policy by inspecting
    every dict in the payload before signing and again after signing,
    raising [`ValueError`][ValueError] if any banned LREG key is
    present (see the module-level guard in
    [`ldtc.attest.exporter`][ldtc.attest.exporter]).

    Args:
        out_dir: Output directory for indicator artifacts. Created on
            demand.
        rate_hz: Maximum export rate in Hz. Floored at `0.1` Hz to
            avoid pathological intervals.
    """

    def __init__(self, out_dir: str, rate_hz: float = 2.0) -> None:
        """Initialize the exporter and ensure `out_dir` exists.

        Args:
            out_dir: Output directory for indicator artifacts.
            rate_hz: Maximum export rate in Hz.
        """
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
        """Export a signed indicator bundle if the rate limit allows.

        Args:
            priv: Ed25519 private key.
            audit: Audit log instance (provides the last hash head).
            derived: Derived indicators from
                [`LREG.derive`][ldtc.guardrails.lreg.LREG.derive] (no raw
                `𝓛` fields).
            cfg: Indicator configuration including profile id.
            last_sc1_pass: Whether SC1 passed in the most recent
                evaluation.

        Returns:
            Tuple `(exported, base_path)`. When the rate limit blocks the
            write, returns `(False, "")`. Otherwise `base_path` is the
            common prefix of the `.jsonl` and `.cbor` files written.

        Raises:
            ValueError: If `derived` or the signed bundle contains any
                raw LREG key.
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
        base = os.path.join(self.out_dir, f"ind_{int(now * 1000)}")
        with open(base + ".jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(bundle, sort_keys=True) + "\n")
        with open(base + ".cbor", "wb") as f:
            f.write(cbor)
        return True, base
