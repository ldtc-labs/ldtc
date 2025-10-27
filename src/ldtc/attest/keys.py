"""Attest: Key management helpers.

Load or generate Ed25519 keys stored as PEM files for device-signed indicators.

See Also:
    paper/main.tex — Methods: Measurement & Attestation.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Tuple

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization


@dataclass
class KeyPaths:
    """Filesystem locations for key files.

    Attributes:
        priv_path: Path to the private key PEM file.
        pub_path: Path to the public key PEM file.
    """

    priv_path: str
    pub_path: str


def ensure_keys(paths: KeyPaths) -> Tuple[Ed25519PrivateKey, Ed25519PublicKey]:
    """Load or generate Ed25519 keys at the provided paths.

    If no keys exist, generates a new keypair and writes them as PEM. If keys
    exist but are not Ed25519, regenerates an Ed25519 pair in place.

    Args:
        paths: Private and public key filesystem paths.

    Returns:
        Tuple ``(private_key, public_key)``.
    """
    os.makedirs(os.path.dirname(paths.priv_path), exist_ok=True)
    if not os.path.exists(paths.priv_path):
        priv = Ed25519PrivateKey.generate()
        pub = priv.public_key()
        with open(paths.priv_path, "wb") as f:
            f.write(
                priv.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                )
            )
        with open(paths.pub_path, "wb") as f:
            f.write(
                pub.public_bytes(
                    serialization.Encoding.PEM,
                    serialization.PublicFormat.SubjectPublicKeyInfo,
                )
            )
        return priv, pub
    else:
        with open(paths.priv_path, "rb") as f:
            loaded_priv = serialization.load_pem_private_key(f.read(), password=None)
        with open(paths.pub_path, "rb") as f:
            loaded_pub = serialization.load_pem_public_key(f.read())
        # Narrow to Ed25519 types if possible
        if isinstance(loaded_priv, Ed25519PrivateKey) and isinstance(
            loaded_pub, Ed25519PublicKey
        ):
            return loaded_priv, loaded_pub
        # If keys are not Ed25519, regenerate Ed25519 keys in-place for consistency
        priv = Ed25519PrivateKey.generate()
        pub = priv.public_key()
        with open(paths.priv_path, "wb") as f:
            f.write(
                priv.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                )
            )
        with open(paths.pub_path, "wb") as f:
            f.write(
                pub.public_bytes(
                    serialization.Encoding.PEM,
                    serialization.PublicFormat.SubjectPublicKeyInfo,
                )
            )
        return priv, pub
