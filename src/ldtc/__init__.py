"""LDTC: Real-time NC1/SC1 verification harness.

This package implements the core primitives described in the LDTC manuscript:

- runtime: fixed-Δt scheduler and windows
- lmeas: estimators, metrics, diagnostics, partitioning
- arbiter: refusal and controller policy
- guardrails: audit, Δt governance, LREG, smell-tests
- attest: device-signed derived indicators
- reporting: timelines, tables, bundles
- omega: perturbation primitives (Ω battery)
- plant: software/hardware adapters and models

Docs: https://docs.ldtc.dev/
"""

from __future__ import annotations

__all__ = [
    "__version__",
]

__version__ = "1.0.0"
