#!/usr/bin/env python3
"""Scripts: Multi-seed LDTC simulation study.

Runs the positive control, the negative controls, the SC1 perturbation
battery, and the command-conflict refusal scenario across ``N`` seeds, using
the *production* CLI handlers (so the study exercises exactly the code paths a
verifier would). Each run's hash-chained audit log is parsed for its outcome,
and the per-seed outcomes are aggregated with bootstrap and Wilson confidence
intervals into machine-readable (JSON/CSV) and paper-ready (LaTeX) tables plus
summary figures.

The seed is the unit of replication: continuous quantities (median ``M``) are
summarized by the mean of per-seed medians with a bootstrap CI, and binary
outcomes (run validity, NC1 / SC1 pass, refusal) by a proportion with a Wilson
score CI.

Run:

    python scripts/study.py --seeds 12 --out artifacts/study

See Also:
    paper/main.tex: Results.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import math
import os
import statistics
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS_DIR = os.path.join(REPO_ROOT, "artifacts", "runs")


# --------------------------------------------------------------------------- #
# Statistics helpers
# --------------------------------------------------------------------------- #
def wilson_ci(k: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    """Wilson score interval for a binomial proportion.

    Args:
        k: Number of successes.
        n: Number of trials.
        z: Normal quantile (1.96 for ~95%).

    Returns:
        ``(lo, hi)`` bounds on the success probability in ``[0, 1]``.
    """
    if n <= 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2.0 * n)) / denom
    half = (z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n))) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def bootstrap_ci(values: List[float], n_boot: int = 2000, seed: int = 0) -> Tuple[float, float]:
    """Percentile bootstrap CI for the mean of ``values``.

    Args:
        values: Sample values (NaNs are dropped).
        n_boot: Number of bootstrap resamples.
        seed: RNG seed for reproducibility.

    Returns:
        ``(lo, hi)`` 95% percentile CI on the mean, or ``(nan, nan)`` if empty.
    """
    arr = np.asarray([v for v in values if v == v], dtype=float)
    if arr.size == 0:
        return (float("nan"), float("nan"))
    if arr.size == 1:
        return (float(arr[0]), float(arr[0]))
    rng = np.random.default_rng(seed)
    boot = rng.choice(arr, size=(n_boot, arr.size), replace=True).mean(axis=1)
    lo, hi = np.percentile(boot, [2.5, 97.5])
    return (float(lo), float(hi))


def _median(values: List[float]) -> float:
    vals = [v for v in values if v == v]
    return float(statistics.median(vals)) if vals else float("nan")


# --------------------------------------------------------------------------- #
# Audit parsing
# --------------------------------------------------------------------------- #
@dataclass
class RunMetrics:
    """Outcome of a single run, parsed from its audit log."""

    scenario: str
    seed: int
    run_dir: str
    valid: bool
    invalidations: List[str]
    Mmin_db: float
    n_windows: int
    M_median: float
    M_min: float
    M_max: float
    nc1_window_frac: float
    nc1_pass: bool
    sc1_evaluated: bool
    sc1_pass: Optional[bool]
    sc1_delta: Optional[float]
    sc1_tau_rec: Optional[float]
    sc1_M_post: Optional[float]
    refusal_evaluated: bool
    refused: Optional[bool]
    refusal_pass: Optional[bool]
    refusal_reasons: List[str]
    trefuse_ms: Optional[float]


def parse_run(scenario: str, seed: int, run_dir: str) -> RunMetrics:
    """Parse a run's audit log into a :class:`RunMetrics`.

    Args:
        scenario: Scenario name.
        seed: Seed used for the run.
        run_dir: Path to the per-run artifact directory.

    Returns:
        Parsed run metrics.
    """
    audit_path = os.path.join(run_dir, "audits", "audit.jsonl")
    Mmin = 3.0
    ms: List[float] = []
    nc1_flags: List[bool] = []
    invalid: List[str] = []
    sc1: Optional[dict] = None
    refusal: Optional[dict] = None
    with open(audit_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            e = json.loads(line)
            ev = e.get("event")
            det = e.get("details", {}) or {}
            if ev == "run_header":
                Mmin = float(det.get("Mmin_db", Mmin))
            elif ev == "window_measured":
                if det.get("M") is not None:
                    ms.append(float(det["M"]))
                nc1_flags.append(bool(det.get("nc1")))
            elif ev == "run_invalidated":
                invalid.append(str(det.get("reason", "?")))
            elif ev == "sc1_result":
                sc1 = det
            elif ev == "command_refusal_result":
                refusal = det

    valid = len(invalid) == 0
    m_med = _median(ms)
    nc1_frac = (sum(1 for f in nc1_flags if f) / len(nc1_flags)) if nc1_flags else 0.0
    nc1_pass = bool(valid and (m_med == m_med) and m_med >= Mmin)

    return RunMetrics(
        scenario=scenario,
        seed=seed,
        run_dir=run_dir,
        valid=valid,
        invalidations=invalid,
        Mmin_db=Mmin,
        n_windows=len(ms),
        M_median=m_med,
        M_min=float(min(ms)) if ms else float("nan"),
        M_max=float(max(ms)) if ms else float("nan"),
        nc1_window_frac=nc1_frac,
        nc1_pass=nc1_pass,
        sc1_evaluated=sc1 is not None,
        sc1_pass=(bool(sc1.get("pass")) if sc1 else None),
        sc1_delta=(float(sc1["delta"]) if sc1 and sc1.get("delta") is not None else None),
        sc1_tau_rec=(float(sc1["tau_rec"]) if sc1 and sc1.get("tau_rec") is not None else None),
        sc1_M_post=(float(sc1["M_post"]) if sc1 and sc1.get("M_post") is not None else None),
        refusal_evaluated=refusal is not None,
        refused=(bool(refusal.get("refused")) if refusal else None),
        refusal_pass=(bool(refusal.get("pass")) if refusal else None),
        refusal_reasons=(list(refusal.get("reasons", [])) if refusal else []),
        trefuse_ms=(
            float(refusal["trefuse_ms_max"]) if refusal and refusal.get("trefuse_ms_max") is not None else None
        ),
    )


# --------------------------------------------------------------------------- #
# Scenario definitions
# --------------------------------------------------------------------------- #
@dataclass
class Scenario:
    """A study scenario: which handler, config, and Ω args to run.

    Attributes:
        name: Stable scenario key used in tables and figures.
        label: Human-readable label.
        kind: One of ``"nc1"``, ``"sc1"``, ``"refusal"`` (selects the headline
            metric for reporting).
        expectation: Short text describing the expected outcome.
        handler: CLI handler name in :mod:`ldtc.cli.main`.
        config: Base YAML profile path (relative to repo root).
        run_tag: Directory-name prefix the handler uses under artifacts/runs.
        omega_args: Extra argparse fields for the handler.
        overrides: Profile overrides applied on top of the base config (used to
            shorten runs for the study without changing the validated dt/window).
    """

    name: str
    label: str
    kind: str
    expectation: str
    handler: str
    config: str
    run_tag: str
    omega_args: Dict[str, Any] = field(default_factory=dict)
    overrides: Dict[str, Any] = field(default_factory=dict)


def default_scenarios() -> List[Scenario]:
    """Return the standard study battery."""
    nc1_over = {"baseline_sec": 12.0, "diag_cadence_windows": 50}
    sc1_over = {"baseline_sec": 8.0, "diag_cadence_windows": 50}
    return [
        Scenario(
            name="positive",
            label="Positive control",
            kind="nc1",
            expectation="NC1 holds (M above Mmin)",
            handler="run_baseline",
            config="configs/profile_r0.yml",
            run_tag="baseline",
            overrides=nc1_over,
        ),
        Scenario(
            name="neg_controller_disabled",
            label="Negative: loop ablated",
            kind="nc1",
            expectation="NC1 fails (M<0), run valid",
            handler="run_baseline",
            config="configs/profile_negative_controller_disabled.yml",
            run_tag="baseline",
            overrides=nc1_over,
        ),
        Scenario(
            name="neg_permanent_ex_flood",
            label="Negative: sustained ex-flood (unshielded)",
            kind="nc1",
            expectation="NC1 fails (M<0); no SC1 recovery",
            handler="omega_ingress_flood",
            config="configs/profile_negative_permanent_ex_flood.yml",
            run_tag="omega-ingress-flood",
            omega_args={"mult": 5.0, "duration": 6.0},
            overrides={"baseline_sec": 10.0, "recovery_observe_sec": 4.0, "diag_cadence_windows": 50},
        ),
        Scenario(
            name="neg_exogenous_subsidy",
            label="Negative: exogenous subsidy",
            kind="nc1",
            expectation="Run invalidated (red flag)",
            handler="omega_exogenous_subsidy",
            config="configs/profile_negative_exogenous_soc.yml",
            run_tag="omega-exogenous-subsidy",
            omega_args={"delta": 0.2, "zero_harvest": True, "duration": 8.0},
            overrides={"baseline_sec": 6.0, "diag_cadence_windows": 50},
        ),
        Scenario(
            name="sc1_power_sag",
            label="SC1: power sag",
            kind="sc1",
            expectation="SC1 holds (recovers)",
            handler="omega_power_sag",
            config="configs/profile_r0.yml",
            run_tag="omega-power-sag",
            omega_args={"drop": 0.3, "duration": 8.0},
            overrides=sc1_over,
        ),
        Scenario(
            name="sc1_ingress_flood",
            label="SC1: ingress flood",
            kind="sc1",
            expectation="SC1 holds (recovers)",
            handler="omega_ingress_flood",
            config="configs/profile_r0.yml",
            run_tag="omega-ingress-flood",
            omega_args={"mult": 5.0, "duration": 8.0},
            overrides=sc1_over,
        ),
        Scenario(
            name="sc1_control_outage",
            label="SC1 designed fail: control outage",
            kind="sc1",
            expectation="SC1 fails (depth bound exceeded)",
            handler="omega_control_outage",
            config="configs/profile_r0.yml",
            run_tag="omega-control-outage",
            omega_args={"duration": 6.0},
            overrides={"baseline_sec": 8.0, "recovery_observe_sec": 10.0, "diag_cadence_windows": 50},
        ),
        Scenario(
            name="refusal_command_conflict",
            label="Threat: command conflict",
            kind="refusal",
            expectation="Refuse at low SoC (<= target latency)",
            handler="omega_command_conflict",
            config="configs/profile_negative_command_conflict.yml",
            run_tag="omega-command-conflict",
            omega_args={"observe": 2.0},
        ),
    ]


# --------------------------------------------------------------------------- #
# Run orchestration (in-process, production handlers)
# --------------------------------------------------------------------------- #
def _load_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return dict(yaml.safe_load(f) or {})


# Threshold keys that R* calibration sets; everything else (dt, window, method,
# p_lag, n_boot) is shared with R0 so the two studies stay directly comparable.
_THRESHOLD_KEYS = ("Mmin_db", "epsilon", "tau_max")


def apply_threshold_profile(scenarios: List[Scenario], profile_path: str) -> List[Scenario]:
    """Inject calibrated decision thresholds into every scenario's overrides.

    The study evaluates NC1/SC1 with the same handler code a verifier runs; the
    only thing that should differ between an "R0" (uncalibrated guess) study and
    the headline "R\\*" study is the decision thresholds (``Mmin_db``,
    ``epsilon``, ``tau_max``). This reads those three keys from ``profile_path``
    and merges them into each scenario's ``overrides`` so the whole battery is
    judged against one consistent, plant-calibrated threshold set.

    Calibration uses a disjoint seed range (see ``calibrate_rstar.py``), so
    evaluating the study seeds against these thresholds is a train/test split,
    not a circular fit.

    Args:
        scenarios: Scenarios to update (copied; inputs are not mutated).
        profile_path: Path to the calibrated profile YAML (``profile_rstar.yml``).

    Returns:
        New scenarios with R* thresholds merged into ``overrides``.
    """
    prof = _load_yaml(profile_path)
    thr = {k: prof[k] for k in _THRESHOLD_KEYS if k in prof}
    if not thr:
        raise ValueError(f"{profile_path} has none of {_THRESHOLD_KEYS}")
    out: List[Scenario] = []
    for s in scenarios:
        ov = dict(s.overrides)
        ov.update(thr)
        out.append(replace(s, overrides=ov))
    return out


def _write_seed_config(base_cfg: Dict[str, Any], seed: int, overrides: Dict[str, Any], tmpdir: str) -> str:
    cfg = dict(base_cfg)
    cfg.update(overrides)
    cfg["seed"] = int(seed)
    cfg["seed_py"] = int(seed)
    cfg["seed_np"] = int(seed)
    path = os.path.join(tmpdir, f"cfg_seed_{seed}.yml")
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, sort_keys=False)
    return path


def _handlers() -> Dict[str, Callable[[argparse.Namespace], None]]:
    from ldtc.cli import main as cli

    return {
        "run_baseline": cli.run_baseline,
        "omega_power_sag": cli.omega_power_sag,
        "omega_ingress_flood": cli.omega_ingress_flood,
        "omega_control_outage": cli.omega_control_outage,
        "omega_exogenous_subsidy": cli.omega_exogenous_subsidy,
        "omega_command_conflict": cli.omega_command_conflict,
    }


def _namespace_for(scn: Scenario, config_path: str) -> argparse.Namespace:
    ns = argparse.Namespace(config=config_path)
    for k, v in scn.omega_args.items():
        setattr(ns, k, v)
    return ns


def _run_header_config(run_dir: str) -> Optional[str]:
    """Return the ``config_path`` recorded in a run's audit header, if any."""
    audit_path = os.path.join(run_dir, "audits", "audit.jsonl")
    if not os.path.exists(audit_path):
        return None
    try:
        with open(audit_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                e = json.loads(line)
                if e.get("event") == "run_header":
                    return e.get("details", {}).get("config_path")
    except Exception:
        return None
    return None


def _find_run_dir(prefix: str, before: set, cfg_path: str) -> Optional[str]:
    """Locate the run directory just created for ``cfg_path``.

    Disambiguates by the unique per-seed config path recorded in the audit
    header, so the harness stays correct even when other runs (e.g., a
    concurrent study) are creating directories at the same time. Falls back to
    the newest directory with the matching tag prefix.

    Args:
        prefix: Expected run-tag prefix (e.g., ``"baseline"``).
        before: Set of directory names present before the handler ran.
        cfg_path: The per-seed config path passed to the handler.

    Returns:
        Absolute path to the matching run directory, or ``None``.
    """
    if not os.path.isdir(RUNS_DIR):
        return None
    new = sorted(set(os.listdir(RUNS_DIR)) - before)
    if not new:
        return None
    target = os.path.abspath(cfg_path)
    for name in new:
        rd = os.path.join(RUNS_DIR, name)
        hdr = _run_header_config(rd)
        if hdr is not None and os.path.abspath(hdr) == target:
            return rd
    # Fallback: newest with the matching tag prefix.
    pref = sorted(n for n in new if n.startswith(prefix))
    return os.path.join(RUNS_DIR, pref[-1]) if pref else None


def run_one(scn: Scenario, seed: int, tmpdir: str, verbose: bool = False) -> Optional[RunMetrics]:
    """Run one scenario at one seed via the production handler and parse it.

    Args:
        scn: Scenario specification.
        seed: Seed for this replicate.
        tmpdir: Directory for the per-seed temporary config.
        verbose: If True, let the handler print to stdout.

    Returns:
        Parsed :class:`RunMetrics`, or ``None`` if no run directory was found.
    """
    handlers = _handlers()
    base_cfg = _load_yaml(os.path.join(REPO_ROOT, scn.config))
    cfg_path = _write_seed_config(base_cfg, seed, scn.overrides, tmpdir)
    ns = _namespace_for(scn, cfg_path)

    before = {d for d in os.listdir(RUNS_DIR)} if os.path.isdir(RUNS_DIR) else set()
    sink = io.StringIO()
    ctx = contextlib.nullcontext() if verbose else contextlib.redirect_stdout(sink)
    with ctx:
        handlers[scn.handler](ns)
    run_dir = _find_run_dir(scn.run_tag, before, cfg_path)
    if run_dir is None:
        return None
    return parse_run(scn.name, seed, run_dir)


# --------------------------------------------------------------------------- #
# Aggregation
# --------------------------------------------------------------------------- #
@dataclass
class Aggregate:
    """Per-scenario aggregate over seeds."""

    name: str
    label: str
    kind: str
    expectation: str
    n_seeds: int
    valid_rate: float
    valid_ci: Tuple[float, float]
    M_mean: float
    M_ci: Tuple[float, float]
    M_median_overall: float
    nc1_pass_rate: float
    nc1_ci: Tuple[float, float]
    sc1_n: int
    sc1_pass_rate: Optional[float]
    sc1_ci: Optional[Tuple[float, float]]
    sc1_delta_median: Optional[float]
    sc1_tau_median: Optional[float]
    refusal_n: int
    refusal_rate: Optional[float]
    refusal_ci: Optional[Tuple[float, float]]
    trefuse_median_ms: Optional[float]
    invalidation_reasons: Dict[str, int]


def aggregate(scn: Scenario, runs: List[RunMetrics]) -> Aggregate:
    """Aggregate per-seed runs into a scenario-level summary.

    Args:
        scn: Scenario specification.
        runs: Per-seed parsed run metrics.

    Returns:
        Scenario-level :class:`Aggregate`.
    """
    n = len(runs)
    valid_k = sum(1 for r in runs if r.valid)
    per_seed_M = [r.M_median for r in runs if r.M_median == r.M_median]
    nc1_k = sum(1 for r in runs if r.nc1_pass)

    sc1_runs = [r for r in runs if r.sc1_evaluated]
    sc1_k = sum(1 for r in sc1_runs if r.sc1_pass)
    sc1_deltas = [r.sc1_delta for r in sc1_runs if r.sc1_delta is not None]
    sc1_taus = [r.sc1_tau_rec for r in sc1_runs if r.sc1_tau_rec is not None]

    ref_runs = [r for r in runs if r.refusal_evaluated]
    ref_k = sum(1 for r in ref_runs if r.refusal_pass)
    ref_lat = [r.trefuse_ms for r in ref_runs if r.trefuse_ms is not None]

    # Count seeds (not windows) that tripped each invalidation reason.
    reasons: Dict[str, int] = {}
    for r in runs:
        for reason in set(r.invalidations):
            reasons[reason] = reasons.get(reason, 0) + 1

    return Aggregate(
        name=scn.name,
        label=scn.label,
        kind=scn.kind,
        expectation=scn.expectation,
        n_seeds=n,
        valid_rate=valid_k / n if n else float("nan"),
        valid_ci=wilson_ci(valid_k, n),
        M_mean=(float(np.mean(per_seed_M)) if per_seed_M else float("nan")),
        M_ci=bootstrap_ci(per_seed_M),
        M_median_overall=_median(per_seed_M),
        nc1_pass_rate=nc1_k / n if n else float("nan"),
        nc1_ci=wilson_ci(nc1_k, n),
        sc1_n=len(sc1_runs),
        sc1_pass_rate=(sc1_k / len(sc1_runs) if sc1_runs else None),
        sc1_ci=(wilson_ci(sc1_k, len(sc1_runs)) if sc1_runs else None),
        sc1_delta_median=(_median(sc1_deltas) if sc1_deltas else None),
        sc1_tau_median=(_median(sc1_taus) if sc1_taus else None),
        refusal_n=len(ref_runs),
        refusal_rate=(ref_k / len(ref_runs) if ref_runs else None),
        refusal_ci=(wilson_ci(ref_k, len(ref_runs)) if ref_runs else None),
        trefuse_median_ms=(_median(ref_lat) if ref_lat else None),
        invalidation_reasons=reasons,
    )


# --------------------------------------------------------------------------- #
# Writers
# --------------------------------------------------------------------------- #
def _fmt_pct(p: float, ci: Tuple[float, float]) -> str:
    if p != p:
        return "--"
    return f"{100*p:.0f}\\% [{100*ci[0]:.0f}, {100*ci[1]:.0f}]"


def _fmt_m(mean: float, ci: Tuple[float, float]) -> str:
    if mean != mean:
        return "--"
    return f"{mean:+.1f} [{ci[0]:+.1f}, {ci[1]:+.1f}]"


def write_csv(aggs: List[Aggregate], path: str) -> None:
    """Write the aggregate results as a flat CSV."""
    import csv

    os.makedirs(os.path.dirname(path), exist_ok=True)
    cols = [
        "scenario",
        "label",
        "kind",
        "expectation",
        "n_seeds",
        "valid_rate",
        "valid_lo",
        "valid_hi",
        "M_mean_db",
        "M_lo",
        "M_hi",
        "M_median_db",
        "nc1_pass_rate",
        "nc1_lo",
        "nc1_hi",
        "sc1_n",
        "sc1_pass_rate",
        "sc1_delta_median",
        "sc1_tau_median",
        "refusal_n",
        "refusal_rate",
        "trefuse_median_ms",
        "invalidations",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for a in aggs:
            w.writerow(
                [
                    a.name,
                    a.label,
                    a.kind,
                    a.expectation,
                    a.n_seeds,
                    f"{a.valid_rate:.4f}",
                    f"{a.valid_ci[0]:.4f}",
                    f"{a.valid_ci[1]:.4f}",
                    f"{a.M_mean:.4f}",
                    f"{a.M_ci[0]:.4f}",
                    f"{a.M_ci[1]:.4f}",
                    f"{a.M_median_overall:.4f}",
                    f"{a.nc1_pass_rate:.4f}",
                    f"{a.nc1_ci[0]:.4f}",
                    f"{a.nc1_ci[1]:.4f}",
                    a.sc1_n,
                    ("" if a.sc1_pass_rate is None else f"{a.sc1_pass_rate:.4f}"),
                    ("" if a.sc1_delta_median is None else f"{a.sc1_delta_median:.4f}"),
                    ("" if a.sc1_tau_median is None else f"{a.sc1_tau_median:.4f}"),
                    a.refusal_n,
                    ("" if a.refusal_rate is None else f"{a.refusal_rate:.4f}"),
                    ("" if a.trefuse_median_ms is None else f"{a.trefuse_median_ms:.4f}"),
                    ";".join(f"{k}={v}" for k, v in a.invalidation_reasons.items()),
                ]
            )


def write_latex(aggs: List[Aggregate], path: str, n_seeds: int) -> None:
    """Write a booktabs LaTeX results table for the paper."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = [
        "% Auto-generated by scripts/study.py -- do not edit by hand.",
        "\\begin{tabular}{llcccc}",
        "\\toprule",
        "Scenario & Expected & Valid & NC1 pass & Median $M$ (dB) & SC1/Refusal \\\\",
        "\\midrule",
    ]
    for a in aggs:
        if a.kind == "sc1":
            last = "--" if a.sc1_pass_rate is None else _fmt_pct(a.sc1_pass_rate, a.sc1_ci or (0, 0))
        elif a.kind == "refusal":
            last = "--" if a.refusal_rate is None else _fmt_pct(a.refusal_rate, a.refusal_ci or (0, 0))
        else:
            last = "--"
        lines.append(
            f"{a.label} & {a.expectation} & {_fmt_pct(a.valid_rate, a.valid_ci)} & "
            f"{_fmt_pct(a.nc1_pass_rate, a.nc1_ci)} & {_fmt_m(a.M_mean, a.M_ci)} & {last} \\\\"
        )
    lines += [
        "\\bottomrule",
        "\\end{tabular}",
        f"% N = {n_seeds} seeds per scenario; brackets are 95% CIs " "(Wilson for proportions, bootstrap for M).",
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def write_json(
    aggs: List[Aggregate],
    runs_by_scn: Dict[str, List[RunMetrics]],
    meta: Dict[str, Any],
    path: str,
) -> None:
    """Write the full study results (aggregates + per-run rows + metadata)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {
        "meta": meta,
        "aggregates": [asdict(a) for a in aggs],
        "runs": {name: [asdict(r) for r in rs] for name, rs in runs_by_scn.items()},
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
def run_study(
    seeds: List[int],
    scenarios: List[Scenario],
    out_dir: str,
    verbose: bool = False,
    threshold_profile: Optional[str] = None,
) -> Tuple[List[Aggregate], Dict[str, List[RunMetrics]]]:
    """Run the full study and write all artifacts.

    Args:
        seeds: Seeds to use as replicates.
        scenarios: Scenarios to run.
        out_dir: Output directory for study artifacts.
        verbose: If True, let handlers print.

    Returns:
        ``(aggregates, runs_by_scenario)``.
    """
    os.environ["LDTC_SKIP_REPORT"] = "1"  # skip per-run figure bundles
    os.makedirs(RUNS_DIR, exist_ok=True)
    runs_by_scn: Dict[str, List[RunMetrics]] = {}
    t0 = time.time()
    with tempfile.TemporaryDirectory(prefix="ldtc_study_") as tmpdir:
        for scn in scenarios:
            rows: List[RunMetrics] = []
            for seed in seeds:
                ts = time.time()
                rm = run_one(scn, seed, tmpdir, verbose=verbose)
                dt = time.time() - ts
                if rm is None:
                    print(f"  [{scn.name}] seed={seed}: NO RUN DIR FOUND", flush=True)
                    continue
                rows.append(rm)
                tag = (
                    f"valid={rm.valid} NC1={rm.nc1_pass} M~{rm.M_median:+.1f}"
                    + (f" SC1={rm.sc1_pass}" if rm.sc1_evaluated else "")
                    + (f" refused={rm.refused}({rm.trefuse_ms}ms)" if rm.refusal_evaluated else "")
                )
                print(f"  [{scn.name}] seed={seed} ({dt:.1f}s): {tag}", flush=True)
            runs_by_scn[scn.name] = rows
            print(f"== {scn.name}: {len(rows)}/{len(seeds)} runs ==", flush=True)

    aggs = [aggregate(scn, runs_by_scn.get(scn.name, [])) for scn in scenarios]
    thr_label = (
        os.path.relpath(threshold_profile, REPO_ROOT) if threshold_profile else "configs/profile_r0.yml (per-scenario)"
    )
    meta = {
        "seeds": seeds,
        "n_seeds": len(seeds),
        "elapsed_sec": round(time.time() - t0, 1),
        "timestamp": time.time(),
        "threshold_profile": thr_label,
        "scenarios": [asdict(s) for s in scenarios],
    }
    write_json(aggs, runs_by_scn, meta, os.path.join(out_dir, "study_results.json"))
    write_csv(aggs, os.path.join(out_dir, "study_results.csv"))
    write_latex(aggs, os.path.join(out_dir, "study_results.tex"), len(seeds))
    return aggs, runs_by_scn


def load_or_run(study_dir: str, seeds: List[int], scenario_names: Optional[List[str]] = None) -> Dict[str, Any]:
    """Load an existing study payload or run a (subset) study to create one.

    Used by the paper figure generators so they always render *real* data: if
    the canonical study has been run (``study_dir/study_results.json`` exists)
    its results are reused; otherwise a small study over ``scenario_names`` is
    run into ``study_dir`` first. Never returns synthetic data.

    Args:
        study_dir: Directory holding (or to hold) ``study_results.json``.
        seeds: Seeds to use if a study must be run.
        scenario_names: Optional subset of scenario names to run.

    Returns:
        The loaded study payload dict.
    """
    path = os.path.join(study_dir, "study_results.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    scns = default_scenarios()
    if scenario_names is not None:
        keep = set(scenario_names)
        scns = [s for s in scns if s.name in keep]
    run_study(seeds, scns, study_dir)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def data_for_paper(
    canonical_dir: str,
    fallback_dir: str,
    seeds: List[int],
    scenario_names: List[str],
) -> Dict[str, Any]:
    """Return study data for a paper figure, preferring the canonical study.

    If the full study (``canonical_dir/study_results.json``) exists it is used
    (e.g., the 15-seed submission run); otherwise a small study over
    ``scenario_names`` is run into ``fallback_dir`` so the figure is still based
    on real data (used by CI paper builds that have no prior study).

    Args:
        canonical_dir: Directory of the full study.
        fallback_dir: Per-figure directory for a small on-demand study.
        seeds: Seeds for the fallback study.
        scenario_names: Scenario subset the figure needs.

    Returns:
        The study payload dict.
    """
    cpath = os.path.join(canonical_dir, "study_results.json")
    if os.path.exists(cpath):
        with open(cpath, "r", encoding="utf-8") as f:
            return json.load(f)
    return load_or_run(fallback_dir, seeds, scenario_names)


def print_summary(aggs: List[Aggregate]) -> None:
    """Print a compact human-readable summary table to stdout."""
    print("\n=== STUDY SUMMARY ===")
    for a in aggs:
        line = (
            f"{a.label:42s} valid={100*a.valid_rate:3.0f}%  "
            f"NC1={100*a.nc1_pass_rate:3.0f}%  M={a.M_mean:+6.1f} dB [{a.M_ci[0]:+.1f},{a.M_ci[1]:+.1f}]"
        )
        if a.kind == "sc1" and a.sc1_pass_rate is not None:
            line += f"  SC1={100*a.sc1_pass_rate:3.0f}% (delta~{a.sc1_delta_median})"
        if a.kind == "refusal" and a.refusal_rate is not None:
            line += f"  refuse={100*a.refusal_rate:3.0f}% (~{a.trefuse_median_ms}ms)"
        print(line)


def main() -> None:
    """CLI entry point for the multi-seed study."""
    ap = argparse.ArgumentParser(description="Run the multi-seed LDTC study and emit tables/figures.")
    ap.add_argument("--seeds", type=int, default=12, help="Number of seeds (replicates) per scenario.")
    ap.add_argument("--seed-base", type=int, default=1000, help="First seed; seeds are base..base+N-1.")
    ap.add_argument("--out", type=str, default=os.path.join(REPO_ROOT, "artifacts", "study"))
    ap.add_argument("--only", type=str, default="", help="Comma-separated scenario names to include.")
    ap.add_argument(
        "--rstar",
        nargs="?",
        const=os.path.join(REPO_ROOT, "configs", "profile_rstar.yml"),
        default="",
        help="Evaluate against calibrated R* thresholds from this profile "
        "(default configs/profile_rstar.yml). Requires running calibrate first.",
    )
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--no-figures", action="store_true", help="Skip figure generation.")
    args = ap.parse_args()

    seeds = [args.seed_base + i for i in range(int(args.seeds))]
    scenarios = default_scenarios()
    if args.only:
        keep = {s.strip() for s in args.only.split(",") if s.strip()}
        scenarios = [s for s in scenarios if s.name in keep]

    if args.rstar:
        if not os.path.exists(args.rstar):
            ap.error(f"--rstar profile not found: {args.rstar} (run `make calibrate` first)")
        scenarios = apply_threshold_profile(scenarios, args.rstar)
        print(f"Evaluating against calibrated thresholds from {args.rstar}", flush=True)

    print(f"Running study: {len(scenarios)} scenarios x {len(seeds)} seeds -> {args.out}", flush=True)
    aggs, runs_by_scn = run_study(
        seeds,
        scenarios,
        args.out,
        verbose=args.verbose,
        threshold_profile=(args.rstar or None),
    )
    print_summary(aggs)

    if not args.no_figures:
        try:
            from study_figures import make_all_figures

            make_all_figures(args.out)
        except Exception as exc:  # pragma: no cover - figures are best-effort
            print(f"(figures skipped: {exc})")

    print(f"\nWrote: {os.path.join(args.out, 'study_results.json')}")
    print(f"Wrote: {os.path.join(args.out, 'study_results.csv')}")
    print(f"Wrote: {os.path.join(args.out, 'study_results.tex')}")


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    main()
