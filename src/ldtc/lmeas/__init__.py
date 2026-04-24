"""Loop-measurement primitives.

`lmeas` is the heart of LDTC's measurement pipeline. It turns a window of
multivariate telemetry into the scalar indicators that NC1 and SC1 are
defined in terms of:

- [`estimators`][ldtc.lmeas.estimators] holds predictive-dependence
  estimators for loop influence `L_loop` and exchange influence `L_ex`,
  plus their bootstrap CIs.
- [`metrics`][ldtc.lmeas.metrics] computes the loop-dominance metric
  `M = 10 · log10(L_loop / L_ex)` (dB) and the SC1 pass / fail
  evaluator.
- [`diagnostics`][ldtc.lmeas.diagnostics] runs stationarity and
  VAR-health checks consumed by smell-tests.
- [`partition`][ldtc.lmeas.partition] manages the `(C, Ex)` partition
  with hysteresis and a greedy regrowth suggestor.

The CLI verification runs feed each window through these modules to
compute the NC1 / SC1 indicators that the
[`attest`][ldtc.attest] subpackage then signs and emits as artifacts.
"""
