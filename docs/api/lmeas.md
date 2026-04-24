# ldtc.lmeas

The "L" measurement subsystem. Computes loop and exchange
predictive influence (`𝓛_loop`, `𝓛_ex`), evaluates the loop-
dominance margin `M (dB)`, decides NC1 / SC1, and manages the
deterministic `(C, Ex)` partition.

| Module | Headline symbols | Use it for |
| ------ | ---------------- | ---------- |
| [`estimators`](#estimators) | [`estimate_L`][ldtc.lmeas.estimators.estimate_L], [`LResult`][ldtc.lmeas.estimators.LResult] | Per-window estimation of `𝓛_loop`, `𝓛_ex` with bootstrapped CIs. Three methods: linear (Granger-like), sklearn MI, Kraskov k-NN MI. |
| [`metrics`](#metrics) | [`m_db`][ldtc.lmeas.metrics.m_db], [`sc1_evaluate`][ldtc.lmeas.metrics.sc1_evaluate], [`SC1Stats`][ldtc.lmeas.metrics.SC1Stats] | Convert `𝓛` to `M (dB)`; evaluate SC1 from baseline / trough / recovery. |
| [`partition`](#partition) | [`Partition`][ldtc.lmeas.partition.Partition], [`PartitionManager`][ldtc.lmeas.partition.PartitionManager], [`greedy_suggest_C`][ldtc.lmeas.partition.greedy_suggest_C] | Maintain `(C, Ex)` with hysteresis; freeze during `Ω`; greedy regrowth proposals. |
| [`diagnostics`](#diagnostics) | [`stationarity_checks`][ldtc.lmeas.diagnostics.stationarity_checks], [`var_nt_ratio`][ldtc.lmeas.diagnostics.var_nt_ratio] | Per-window ADF / KPSS and VAR `N / T` ratio diagnostics surfaced into the audit. |

::: ldtc.lmeas
    options:
      members: false
      show_root_heading: false
      show_source: false

## estimators

::: ldtc.lmeas.estimators

## metrics

::: ldtc.lmeas.metrics

## partition

::: ldtc.lmeas.partition

## diagnostics

::: ldtc.lmeas.diagnostics
