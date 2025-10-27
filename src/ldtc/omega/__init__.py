"""Ω (Omega) perturbation modules for LDTC.

This package provides stimulus primitives used in the verification pipeline:

- ``power_sag``: reduce harvest/power input transiently
- ``ingress_flood``: burst external demand/I/O
- ``command_conflict``: issue a risky command to exercise refusal logic

These are surfaced in the CLI and examples and referenced in the paper's
Verification Pipeline and Signatures sections.
"""
