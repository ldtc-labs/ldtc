"""Runtime utilities for fixed-interval scheduling and sliding windows.

This subpackage provides:

- ``FixedScheduler``: a lightweight, fixed-Δt scheduler with jitter metrics
- ``SlidingWindow``: per-channel, fixed-capacity windowing for telemetry

These building blocks are used by the CLI runs and verification harness.
"""
