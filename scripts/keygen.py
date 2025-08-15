#!/usr/bin/env python3
from __future__ import annotations

import os

from ldtc.attest.keys import ensure_keys, KeyPaths


def main() -> None:
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
