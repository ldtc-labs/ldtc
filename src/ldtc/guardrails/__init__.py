"""Guardrails and governance for LDTC runs.

Components include:

- ``audit``: append-only, hash-chained audit log
- ``dt_guard``: privileged Δt governance with rate limits
- ``lreg``: enclave-like register for raw L/CI with derived-indicator export
- ``smelltests``: measurement fragility and anti-gaming checks
"""
