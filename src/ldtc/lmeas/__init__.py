"""Loop-measurement (lmeas) primitives for LDTC.

This subpackage implements:

- ``estimators`` for loop/exchange influence (L)
- ``metrics`` such as decibel loop-dominance and SC1 evaluation
- ``diagnostics`` for stationarity and VAR health
- ``partition`` management and greedy regrowth with hysteresis

These are used by the CLI verification runs to compute NC1/SC1 indicators.
"""
