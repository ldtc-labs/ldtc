#!/usr/bin/env python3
"""Scripts: Generate Ed25519 keypair for attestation.

Writes PEM-encoded private and public keys under ``artifacts/keys`` using the
same paths expected by the CLI and verification scripts.
"""
from __future__ import annotations

import os

from ldtc.attest.keys import ensure_keys, KeyPaths


def main() -> None:
    """Generate keys and print file locations.

    Creates keys if missing or replaces keys with Ed25519 format if needed.
    """
    kp = KeyPaths(
        priv_path=os.path.join("artifacts", "keys", "ed25519_priv.pem"),
        pub_path=os.path.join("artifacts", "keys", "ed25519_pub.pem"),
    )
    priv, pub = ensure_keys(kp)
    print("Wrote keys:")
    print("  ", kp.priv_path)
    print("  ", kp.pub_path)


if __name__ == "__main__":
    main()
