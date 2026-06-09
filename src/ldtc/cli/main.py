"""LDTC CLI: orchestrate baseline and `Ω` perturbation runs.

This module is the verification harness's "main loop": it loads a YAML
profile, wires together the runtime scheduler
([`runtime`][ldtc.runtime]), measurement estimators
([`lmeas`][ldtc.lmeas]), guardrails ([`guardrails`][ldtc.guardrails]),
attestation ([`attest`][ldtc.attest]), the refusal arbiter and policy
([`arbiter`][ldtc.arbiter]), the plant adapter
([`plant`][ldtc.plant]), and finally the reporting bundle
([`reporting`][ldtc.reporting]).

Subcommands map one-to-one to functions in this module:

| Subcommand | Function |
| ---------- | -------- |
| `ldtc run` | [`run_baseline`][ldtc.cli.main.run_baseline] |
| `ldtc omega-power-sag` | [`omega_power_sag`][ldtc.cli.main.omega_power_sag] |
| `ldtc omega-ingress-flood` | [`omega_ingress_flood`][ldtc.cli.main.omega_ingress_flood] |
| `ldtc omega-command-conflict` | [`omega_command_conflict`][ldtc.cli.main.omega_command_conflict] |
| `ldtc omega-exogenous-subsidy` | [`omega_exogenous_subsidy`][ldtc.cli.main.omega_exogenous_subsidy] |

Each handler follows the same five-stage shape:

1. Load profile and seed RNGs.
2. Build adapters, audit log, LREG, exporter, scheduler, and
   guardrails.
3. Run a baseline phase, optionally an `Ω` window, and a recovery
   phase, all gated by [`SmellConfig`][ldtc.guardrails.smelltests.SmellConfig].
4. After the scheduler stops, perform post-run audit checks (chain
   integrity, no raw LREG leakage).
5. Build a verification artifact bundle via
   [`reporting.artifacts.bundle`][ldtc.reporting.artifacts.bundle].

See Also:
    `paper/main.tex`: Verification Pipeline; CLI orchestration.
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import time
from typing import TYPE_CHECKING, Any, Dict, List, Protocol

import numpy as np
import yaml

from ..arbiter.policy import ControllerPolicy
from ..arbiter.refusal import RefusalArbiter
from ..attest.exporter import IndicatorExporter
from ..attest.indicators import IndicatorConfig
from ..attest.keys import KeyPaths, ensure_keys
from ..guardrails.audit import AuditLog
from ..guardrails.dt_guard import DeltaTGuard, DtGuardConfig
from ..guardrails.lreg import LREG, LEntry
from ..guardrails.smelltests import (
    SmellConfig,
    audit_chain_broken,
    audit_contains_raw_lreg_values,
    exogenous_subsidy_red_flag,
    invalid_by_ci,
    invalid_by_ci_history,
    invalid_by_partition_flips,
    invalid_flip_during_omega,
)
from ..lmeas.estimators import estimate_L
from ..lmeas.metrics import m_db, sc1_evaluate
from ..lmeas.partition import PartitionManager, greedy_suggest_C
from ..plant.adapter import PlantAdapter
from ..reporting.artifacts import bundle as build_verification_bundle
from ..runtime.sim import make_driver
from ..runtime.windows import SlidingWindow

if TYPE_CHECKING:
    from ..plant.models import Action as PlantAction


class AdapterProtocol(Protocol):
    """Structural protocol for plant adapters used by the CLI.

    Both [`PlantAdapter`][ldtc.plant.adapter.PlantAdapter] and
    [`HardwarePlantAdapter`][ldtc.plant.hw_adapter.HardwarePlantAdapter]
    satisfy this protocol; the CLI uses it so that `_make_adapter_from_profile`
    can transparently swap implementations based on the `plant.adapter`
    profile field.
    """

    def read_state(self) -> Dict[str, float]:
        """Return the latest plant state as a dict of named floats."""
        ...

    def write_actuators(self, action: "PlantAction") -> None:  # noqa: F821
        """Send actuator commands to the plant."""
        ...

    def apply_omega(self, name: str, **kwargs: float) -> Dict[str, float | str]:
        """Forward an `Ω` request and return a small status dict."""
        ...


def _load_yaml(path: str) -> Dict:
    """Load a YAML configuration file.

    Args:
        path: Filesystem path to a YAML file.

    Returns:
        Parsed configuration dictionary.
    """
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _set_seeds(prof: Dict) -> Dict[str, int]:
    """Configure global RNG seeds from a config dict.

    Resolves the per-stream seeds from the profile, defaulting to
    `12345` when none are set. The resolved seeds are returned so the
    CLI can record them in the audit `run_header`.

    Args:
        prof: Configuration dictionary possibly containing `seed`,
            `seed_py`, and `seed_np`. `seed_py` and `seed_np` take
            precedence over `seed`.

    Returns:
        Dict with concrete `seed_py` and `seed_np` values.
    """
    seed = prof.get("seed")
    seed_py = int(prof.get("seed_py", seed if seed is not None else 12345))
    seed_np = int(prof.get("seed_np", seed if seed is not None else 12345))
    random.seed(seed_py)
    np.random.seed(seed_np)
    return {"seed_py": seed_py, "seed_np": seed_np}


def _print_and_audit_header(audit: AuditLog, header: Dict) -> None:
    """Print the run header to stdout and append it to the audit log.

    Args:
        audit: Audit log used to record the header as a `run_header`
            event.
        header: Header fields (profile id, `Δt`, window, thresholds,
            seeds, `Ω` name and args).
    """
    msg = (
        f"profile_id={header.get('profile_id')} dt={header.get('dt')} window_sec={header.get('window_sec')} "
        f"method={header.get('method')} p_lag={header.get('p_lag')} mi_lag={header.get('mi_lag')} "
        f"Mmin_db={header.get('Mmin_db')} epsilon={header.get('epsilon')} tau_max={header.get('tau_max')} "
        f"seed_py={header.get('seed_py')} seed_np={header.get('seed_np')} omega={header.get('omega','-')} "
        f"omega_args={header.get('omega_args',{})}"
    )
    print("Run header:", msg)
    audit.append("run_header", header)


def _human_invalidation_reason(reason: str, details: Dict) -> str:
    """Render an invalidation reason as a human-readable string.

    The audit log records short machine-friendly reason codes (e.g.,
    `ci_inflation`, `dt_jitter_excess`); this helper turns each into a
    longer explanation suitable for the CLI footer.

    Args:
        reason: Machine-friendly reason code.
        details: Reason-specific details such as `flips_per_hour`,
            `jitter_p95_rel`, or CI bounds.

    Returns:
        Human-readable explanation, or the raw `reason` if no humanizer
        is registered.
    """
    try:
        if reason == "ci_inflation":
            hwL = (
                0.5 * abs((details.get("ci_loop", (0, 0))[1]) - (details.get("ci_loop", (0, 0))[0]))
                if "ci_loop" in details
                else None
            )
            hwE = (
                0.5 * abs((details.get("ci_ex", (0, 0))[1]) - (details.get("ci_ex", (0, 0))[0]))
                if "ci_ex" in details
                else None
            )
            mx = max([v for v in (hwL, hwE) if v is not None] or [None])
            return f"CI half-width exceeded 0.30 (max≈{mx:.2f})"
        if reason == "ci_history_inflation":
            med_loop = details.get("median_hw_loop")
            med_ex = details.get("median_hw_ex")
            base_loop = details.get("baseline_hw_loop")
            base_ex = details.get("baseline_hw_ex")
            return (
                "CI medians over lookback exceeded limits "
                f"(loop≈{med_loop:.2f}, ex≈{med_ex:.2f}; "
                f"baseline loop≈{base_loop:.2f}, ex≈{base_ex:.2f}; "
                "max=0.30, inflate≥2.0×)"
            )
        if reason == "partition_flapping":
            rate = details.get("flips_per_hour")
            flips = details.get("flips")
            return f"Partition flapping: {flips} flips (~{rate:.1f}/hr) > limit (2/hr)"
        if reason == "partition_flip_during_omega":
            return "Partition flipped during Ω window (forbidden)"
        if reason == "dt_change_rate_limit":
            ch = details.get("changes_this_hour")
            min_gap = details.get("min_gap_s")
            return f"Δt edit rate exceeded (changes this hour={ch}, min gap={min_gap}s; limit=3/hr)"
        if reason == "dt_jitter_excess":
            rel = details.get("jitter_p95_rel")
            return f"Scheduler jitter p95 exceeded 0.25×Δt (rel≈{rel:.2f})"
        if reason == "audit_chain_broken":
            return "Audit chain broken (counter/hash/timestamp check failed)"
        if reason == "raw_lreg_breach":
            return "Raw LREG fields appeared in audit (policy breach)"
        if reason == "exogenous_subsidy_red_flag":
            return "Exogenous subsidy red-flag (M rising with high I/O or SoC rising without harvest)"
    except Exception:
        pass
    return reason


def _append_invalidation(audit: AuditLog, reason: str, details: Dict, _sink: Dict) -> None:
    """Append a `run_invalidated` event with a human-readable reason.

    Args:
        audit: Target audit log.
        reason: Machine-friendly reason code.
        details: Reason-specific fields, copied into the audit record.
        _sink: Caller-provided dict used as a thin out-parameter; the
            human-readable reason is stored at
            `_sink["last_invalidation_human"]` so callers that print a
            CLI footer can recover it without re-reading the audit.
    """
    rh = _human_invalidation_reason(reason, details)
    det = {"reason": reason, **details, "reason_human": rh}
    audit.append("run_invalidated", det)
    _sink["last_invalidation_human"] = rh


def _print_invalidation_footer(audit_path: str) -> None:
    """Print the latest invalidation reason at the bottom of a CLI run.

    Args:
        audit_path: Path to the JSONL audit log produced by the run.
    """
    try:
        import json as _json

        last = None
        with open(audit_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                obj = _json.loads(line)
                if obj.get("event") == "run_invalidated":
                    last = obj
        if last is not None:
            det = last.get("details", {}) or {}
            human = det.get("reason_human") or _human_invalidation_reason(det.get("reason", ""), det)
            print(f"Run invalidated: {human}")
    except Exception:
        pass


def _ensure_dirs(tag: str = "run") -> Dict[str, str]:
    """Create and return per-run artifact subdirectories.

    Each invocation gets its own isolated directory under
    `artifacts/runs/<tag>-<timestamp>/`. Isolation is required for the
    hash-chained audit log: appending consecutive runs to a single shared
    `audit.jsonl` would break the counter/hash continuity and (correctly)
    trip the `audit_chain_broken` smell-test. Signing keys remain shared
    under `artifacts/keys/`.

    Args:
        tag: Short label for the run (e.g., `"baseline"`, `"omega-power-sag"`)
            used as a filename-friendly prefix.

    Returns:
        Dict with `artifacts`, `run`, `audits`, `indicators`, and `figures`
        keys mapping to absolute paths.
    """
    import datetime as _dt
    import uuid as _uuid

    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_id = f"{tag}-{stamp}-{_uuid.uuid4().hex[:6]}"
    artifacts = os.path.join("artifacts")
    run_dir = os.path.join(artifacts, "runs", run_id)
    audits = os.path.join(run_dir, "audits")
    indicators = os.path.join(run_dir, "indicators")
    figures = os.path.join(run_dir, "figures")
    os.makedirs(audits, exist_ok=True)
    os.makedirs(indicators, exist_ok=True)
    os.makedirs(figures, exist_ok=True)
    return {
        "artifacts": artifacts,
        "run": run_dir,
        "audits": audits,
        "indicators": indicators,
        "figures": figures,
    }


def _make_adapter_from_profile(prof: Dict) -> AdapterProtocol:
    """Build a plant adapter from the `plant.*` block of a profile.

    Args:
        prof: Loaded YAML profile dict. The `plant.adapter` field
            selects the implementation: `"sim"` / `"software"` /
            `"inproc"` returns a
            [`PlantAdapter`][ldtc.plant.adapter.PlantAdapter] over the
            in-process software model; `"hardware"` / `"hw"` lazily
            imports
            [`HardwarePlantAdapter`][ldtc.plant.hw_adapter.HardwarePlantAdapter]
            and configures its transport.

    Returns:
        An object satisfying
        [`AdapterProtocol`][ldtc.cli.main.AdapterProtocol].

    Raises:
        ValueError: If `plant.adapter` is not a recognized kind.
        RuntimeError: If hardware adapter is requested but its optional
            dependencies are not installed.
    """
    plant_prof = prof.get("plant", {}) or {}
    adapter_kind = str(plant_prof.get("adapter", "sim")).lower()
    if adapter_kind in ("sim", "software", "inproc"):
        from ..plant.models import Plant, PlantParams

        # Optional plant-parameter overrides from the profile.
        param_overrides = plant_prof.get("params", {}) or {}
        valid_fields = set(PlantParams().__dict__.keys())
        clean = {k: v for k, v in param_overrides.items() if k in valid_fields}
        params = PlantParams(**clean) if clean else PlantParams()
        # The loop is disengaged for the controller-disabled negative control,
        # turning the plant into passive matter driven by exchange.
        loop_engaged = not bool(prof.get("controller_disabled", False))
        loop_engaged = bool(plant_prof.get("loop_engaged", loop_engaged))
        return PlantAdapter(Plant(params=params, loop_engaged=loop_engaged))
    if adapter_kind in ("hardware", "hw"):
        try:
            from ..plant.hw_adapter import HardwarePlantAdapter as _HardwarePlantAdapter
        except Exception as e:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "HardwarePlantAdapter unavailable. Ensure optional deps (e.g., pyserial) are installed if using serial."
            ) from e
        transport = str(plant_prof.get("transport", "udp"))
        return _HardwarePlantAdapter(
            transport=transport,
            udp_bind_host=str(plant_prof.get("udp_bind_host", "0.0.0.0")),
            udp_bind_port=int(plant_prof.get("udp_bind_port", 5005)),
            udp_control_host=plant_prof.get("udp_control_host"),
            udp_control_port=plant_prof.get("udp_control_port"),
            serial_port=str(plant_prof.get("serial_port", "/dev/ttyUSB0")),
            serial_baud=int(plant_prof.get("serial_baud", 115200)),
            telemetry_timeout_sec=float(plant_prof.get("telemetry_timeout_sec", 2.0)),
        )
    raise ValueError(f"Unknown plant.adapter kind: {adapter_kind}")


def _emit_window_diagnostics(
    audit: AuditLog,
    X: "np.ndarray",
    p_lag: int,
    method: str,
    idx: int,
    cadence: int,
) -> List[str]:
    """Emit per-window diagnostics, gating the expensive stationarity tests.

    The VAR samples-per-parameter ratio is cheap and always reported. The
    ADF / KPSS stationarity tests are comparatively expensive (seconds over a
    full run), so they run only every `cadence` windows. This keeps long
    simulation studies tractable without weakening the guards: by
    construction the plant processes are stationary, and periodic checks
    still catch a genuine drift into an ill-posed regime.

    Args:
        audit: Audit log to append `window_diagnostics` /
            `measurement_unstable` records to.
        X: Window matrix of shape `(T, N)`.
        p_lag: VAR lag order used by the linear estimator.
        method: Estimator method (`measurement_unstable` is only emitted for
            `"linear"`, which is the method sensitive to these conditions).
        idx: Window index (used for cadence gating).
        cadence: Run stationarity tests every `cadence` windows (`<= 1`
            means every window).

    Returns:
        List of instability reason codes detected this window (possibly
        empty).
    """
    reasons: List[str] = []
    try:
        from ..lmeas.diagnostics import var_nt_ratio

        vratio = var_nt_ratio(T=X.shape[0], N=X.shape[1], p=p_lag)
        det: Dict[str, object] = {
            "var_nt_ratio": round(float(vratio), 3),
            "var_marginal": bool(vratio < 1.5),
        }
        if vratio < 1.5:
            reasons.append("var_nt_ratio_low")
        run_stat = (cadence <= 1) or (idx % cadence == 0)
        if run_stat:
            from ..lmeas.diagnostics import stationarity_checks

            stn = stationarity_checks(X)
            det["adf_ns_frac"] = round(float(stn.adf_nonstationary_frac), 3)
            det["kpss_ns_frac"] = round(float(stn.kpss_nonstationary_frac), 3)
            if float(stn.adf_nonstationary_frac) > 0.5:
                reasons.append("adf_nonstationary_high")
            if float(stn.kpss_nonstationary_frac) > 0.5:
                reasons.append("kpss_nonstationary_high")
        audit.append("window_diagnostics", det)
        if method == "linear" and reasons:
            unstable: Dict[str, Any] = {"reasons": reasons}
            for k in ("adf_ns_frac", "kpss_ns_frac", "var_nt_ratio"):
                if k in det:
                    unstable[k] = det[k]
            audit.append("measurement_unstable", unstable)
    except Exception:
        pass
    return reasons


def run_baseline(args: argparse.Namespace) -> None:
    """Run the baseline NC1 verification loop.

    Performs the standard verification harness loop: a fixed-`Δt`
    scheduler streams plant telemetry into a sliding window, the
    [`lmeas`][ldtc.lmeas] estimator computes `M (dB)` per window,
    [`guardrails`][ldtc.guardrails] watch for invalidation conditions,
    and [`attest`][ldtc.attest] periodically signs derived indicators.
    A verification artifact bundle is built at the end via
    [`reporting.artifacts.bundle`][ldtc.reporting.artifacts.bundle].

    Args:
        args: Parsed argparse namespace; the only required field is
            `--config`, the path to a YAML profile (e.g.,
            `configs/profile_R0.yml`).
    """
    prof = _load_yaml(args.config)
    seeds = _set_seeds(prof)
    dt = float(prof.get("dt", 0.01))
    window_sec = float(prof.get("window_sec", 0.2))
    window = max(4, int(window_sec / dt))
    method = str(prof.get("method", "linear"))
    Mmin = float(prof.get("Mmin_db", 3.0))
    p_lag = int(prof.get("p_lag", 3))
    mi_lag = int(prof.get("mi_lag", 1))
    n_boot = int(prof.get("n_boot", 32))
    mi_k = int(prof.get("mi_k", 5))
    # Partition growth hysteresis config
    part_delta_M_min_db = float(prof.get("part_delta_M_min_db", 0.5))
    part_consecutive_required = int(prof.get("part_consecutive_required", 3))
    part_growth_cadence_windows = int(prof.get("part_growth_cadence_windows", 5))
    # Partition growth is an optional exploratory feature; off by default so the
    # designed self-maintenance set (energy/temperature/health) is the C used
    # for the loop-dominance test and the partition cannot flap.
    part_growth_enabled = bool(prof.get("part_growth_enabled", False))
    # Greedy ΔL_loop gain knobs with sparsity penalty and cap
    part_lambda = float(prof.get("part_lambda", 0.0))
    part_theta = float(prof.get("part_theta", 0.0))
    part_kappa_val = prof.get("part_kappa")
    part_kappa = int(part_kappa_val) if part_kappa_val is not None else None

    dirs = _ensure_dirs("baseline")
    audit = AuditLog(os.path.join(dirs["audits"], "audit.jsonl"))
    audit.append("baseline_start", {"config": args.config})
    _print_and_audit_header(
        audit,
        {
            "profile_id": int(prof.get("profile_id", 0)),
            "config_path": str(args.config),
            "dt": dt,
            "window_sec": window_sec,
            "method": method,
            "p_lag": p_lag,
            "mi_lag": mi_lag,
            "Mmin_db": Mmin,
            "epsilon": float(prof.get("epsilon", 0.15)),
            "tau_max": float(prof.get("tau_max", 60.0)),
            "mi_k": mi_k,
            **seeds,
            "omega": "baseline",
            "omega_args": {},
        },
    )
    # plant
    adapter = _make_adapter_from_profile(prof)
    # measurement buffers
    order = ["E", "T", "R", "demand", "io", "H"]
    sw = SlidingWindow(capacity=window, channel_order=order)

    # C partition: internal states [E, T, R] -> indices 0,1,2
    pm = PartitionManager(N_signals=len(order), seed_C=[0, 1, 2])
    # guardrails and attest
    lreg = LREG()
    refusal = RefusalArbiter(Mmin_db=Mmin)
    policy = ControllerPolicy(refusal=refusal)
    kp = KeyPaths(
        priv_path=os.path.join("artifacts", "keys", "ed25519_priv.pem"),
        pub_path=os.path.join("artifacts", "keys", "ed25519_pub.pem"),
    )
    priv, pub = ensure_keys(kp)
    exporter = IndicatorExporter(out_dir=dirs["indicators"], rate_hz=2.0)
    icfg = IndicatorConfig(Mmin_db=Mmin, profile_id=int(prof.get("profile_id", 0)))

    # Controller disable (negative control) via config
    controller_disabled = bool(prof.get("controller_disabled", False))
    # main tick
    risky_cmd = None  # filled by Ω in other commands; baseline has none

    start_time = time.perf_counter()
    cfg_smell = SmellConfig()
    # Histories for smell tests
    ci_loop_hist = []
    ci_ex_hist = []
    baseline_hw_medians = None
    M_hist = []
    io_hist = []
    E_hist = []
    H_hist = []

    window_idx = 0
    last_flip_count = 0

    def tick(_now: float) -> None:
        nonlocal risky_cmd, window_idx, last_flip_count, baseline_hw_medians
        state = adapter.read_state()
        # quick-and-dirty predicted M: use last entry if exists
        ent = lreg.latest()
        predicted = ent.M_db if ent else 0.0
        if controller_disabled:
            # Zero control action, always accept commands
            from ..arbiter.policy import ControlAction

            act = ControlAction(throttle=0.0, cool=0.0, repair=0.0, accept_cmd=True)
            policy.last_decision = None
        else:
            act = policy.compute(state, predicted_M_db=predicted, risky_cmd=risky_cmd)
        # plant step
        from ..plant.models import Action as PlantAction

        adapter.write_actuators(action=PlantAction(**act.__dict__))
        # measure
        state2 = adapter.read_state()
        sw.append(state2)
        if sw.ready():
            X = np.asarray(sw.get_matrix())
            part = pm.get()
            res = estimate_L(
                X=X,
                C=part.C,
                Ex=part.Ex,
                method=method,
                p=p_lag,
                lag_mi=mi_lag,
                n_boot=n_boot,
                mi_k=mi_k,
            )
            # Diagnostics: stationarity + VAR N/T ratio (stationarity gated by
            # cadence to keep long studies tractable; no raw LREG values).
            _emit_window_diagnostics(
                audit,
                X,
                p_lag,
                method,
                int(lreg.derive().get("counter", 0)),
                int(prof.get("diag_cadence_windows", 1)),
            )
            M = m_db(res.L_loop, res.L_ex)
            nc1 = M >= Mmin
            # smell tests
            # Update histories
            ci_loop_hist.append(res.ci_loop)
            ci_ex_hist.append(res.ci_ex)
            M_hist.append(M)
            E_hist.append(state2.get("E", 0.0))
            io_hist.append(state2.get("io", 0.0))
            H_hist.append(state2.get("H", 0.0))
            # Establish baseline CI medians (once) after we have lookback windows
            if baseline_hw_medians is None and len(ci_loop_hist) >= cfg_smell.ci_lookback_windows:
                recent_loop = ci_loop_hist[-cfg_smell.ci_lookback_windows :]
                recent_ex = ci_ex_hist[-cfg_smell.ci_lookback_windows :]
                hw_loop_list = sorted([0.5 * abs(lohi[1] - lohi[0]) for lohi in recent_loop])
                hw_ex_list = sorted([0.5 * abs(lohi[1] - lohi[0]) for lohi in recent_ex])
                baseline_hw_medians = (
                    hw_loop_list[len(hw_loop_list) // 2],
                    hw_ex_list[len(hw_ex_list) // 2],
                )
            # Smell tests
            if invalid_by_ci(res.ci_loop, res.ci_ex, cfg_smell):
                lreg.invalidate("ci_inflation")
                try:
                    hwL = 0.5 * abs(res.ci_loop[1] - res.ci_loop[0])
                    hwE = 0.5 * abs(res.ci_ex[1] - res.ci_ex[0])
                except Exception:
                    hwL, hwE = None, None
                _append_invalidation(
                    audit,
                    "ci_inflation",
                    {
                        "halfwidth_loop": hwL,
                        "halfwidth_ex": hwE,
                        "max_allowed": cfg_smell.max_ci_halfwidth,
                    },
                    _sink={},
                )
            if invalid_by_ci_history(ci_loop_hist, ci_ex_hist, cfg_smell, baseline_hw_medians):
                lreg.invalidate("ci_history_inflation")
                med_loop: float | None = None
                med_ex: float | None = None
                b_loop: float | None = None
                b_ex: float | None = None
                try:
                    n = cfg_smell.ci_lookback_windows
                    rL = ci_loop_hist[-n:]
                    rE = ci_ex_hist[-n:]
                    hwL_list = sorted([0.5 * abs(lohi[1] - lohi[0]) for lohi in rL])
                    hwE_list = sorted([0.5 * abs(lohi[1] - lohi[0]) for lohi in rE])
                    med_loop = hwL_list[n // 2]
                    med_ex = hwE_list[n // 2]
                    if baseline_hw_medians:
                        b_loop, b_ex = baseline_hw_medians
                except Exception:
                    pass
                _append_invalidation(
                    audit,
                    "ci_history_inflation",
                    {
                        "median_hw_loop": med_loop,
                        "median_hw_ex": med_ex,
                        "baseline_hw_loop": b_loop,
                        "baseline_hw_ex": b_ex,
                        "max_allowed": cfg_smell.max_ci_halfwidth,
                        "inflate_factor": cfg_smell.ci_inflate_factor,
                    },
                    _sink={},
                )
            # Δt governance invalidation propagated from guard
            if dt_guard.invalidated and not lreg.invalidated:
                lreg.invalidate("dt_change_rate_limit")
                # audit already appended by guard
            # partition flip-rate guard
            elapsed = max(1e-6, time.perf_counter() - start_time)
            if invalid_by_partition_flips(pm.get().flips, elapsed, cfg_smell):
                lreg.invalidate("partition_flapping")
                rate = 3600.0 * (float(pm.get().flips) / max(1e-6, float(elapsed)))
                _append_invalidation(
                    audit,
                    "partition_flapping",
                    {
                        "flips": pm.get().flips,
                        "elapsed_sec": elapsed,
                        "flips_per_hour": rate,
                        "limit_per_hour": cfg_smell.max_partition_flips_per_hour,
                    },
                    _sink={},
                )
            # Exogenous subsidy red flags (heuristic)
            if exogenous_subsidy_red_flag(M_hist, io_hist, E_hist, H_hist, cfg_smell):
                lreg.invalidate("exogenous_subsidy")
                _append_invalidation(audit, "exogenous_subsidy_red_flag", {}, _sink={})
            idx = lreg.write(
                LEntry(
                    L_loop=res.L_loop,
                    L_ex=res.L_ex,
                    ci_loop=res.ci_loop,
                    ci_ex=res.ci_ex,
                    M_db=M,
                    nc1_pass=nc1,
                )
            )
            audit.append(
                "window_measured",
                {"idx": idx, "M": M, "nc1": nc1, "partition_flips": pm.get().flips},
            )
            # export indicators (derived only)
            derived = lreg.derive()
            exported, base = exporter.maybe_export(priv, audit, derived, icfg, last_sc1_pass=False)
            if exported:
                audit.append("indicators_exported", {"base": os.path.basename(base)})
            # Deterministic growth cadence with hysteresis (skip if frozen)
            window_idx += 1
            if part_growth_enabled and (window_idx % part_growth_cadence_windows) == 0 and not pm.get().frozen:
                part = pm.get()
                # Greedy ΔL_loop suggestor with sparsity penalty and κ-cap
                cand_C, dM_db, greedy_details = greedy_suggest_C(
                    X=X,
                    C=part.C,
                    Ex=part.Ex,
                    estimator=estimate_L,
                    method=method,
                    p=p_lag,
                    lag_mi=mi_lag,
                    n_boot_candidates=max(8, n_boot // 4),
                    mi_k=mi_k,
                    lam=part_lambda,
                    theta=part_theta,
                    kappa=part_kappa,
                )
                if cand_C != part.C:
                    pm.maybe_regrow(
                        cand_C,
                        delta_M_db=float(dM_db),
                        delta_M_min_db=part_delta_M_min_db,
                        consecutive_required=part_consecutive_required,
                    )
                    if pm.get().flips != last_flip_count:
                        info = getattr(pm, "last_flip_info", None)
                        details = {
                            "flips": pm.get().flips,
                            "new_C": pm.get().C,
                            "greedy_added": greedy_details.get("added", []),
                            "greedy_step_gains": greedy_details.get("step_gains", []),
                            "greedy_M_base": greedy_details.get("M_base"),
                            "greedy_M_final": greedy_details.get("M_final"),
                        }
                        if info is not None:
                            details.update(
                                {
                                    "delta_M_db": info.get("delta_M_db"),
                                    "hysteresis_streak": info.get("streak"),
                                    "candidate_C": info.get("new_C"),
                                }
                            )
                        audit.append("partition_flip", details)
                        last_flip_count = pm.get().flips

    def _audit_hook(ev: str, det: dict) -> None:
        # Discard return value; hook contract expects None
        audit.append(ev, det)
        return None

    # Δt governance guard
    dt_guard_cfg = DtGuardConfig(
        max_changes_per_hour=int(prof.get("max_dt_changes_per_hour", 3)),
        min_seconds_between_changes=float(prof.get("min_seconds_between_changes", 1.0)),
    )
    dt_guard = DeltaTGuard(audit=audit, cfg=dt_guard_cfg)
    sch = make_driver(prof, dt, tick, _audit_hook, dt_guard)
    try:
        sch.start()
        # Run for requested seconds (default 10)
        run_sec = float(prof.get("baseline_sec", 10.0))
        sch.run_for(run_sec)
    finally:
        stats = sch.stop()
        audit.append("baseline_stop", {"ticks": stats.ticks})
        # Δt jitter smell-test: invalidate if p95(|jitter|)/dt exceeds threshold
        if (stats.jitter_p95_abs / max(1e-9, dt)) > SmellConfig().jitter_p95_rel_max:
            lreg.invalidate("dt_jitter_excess")
            _append_invalidation(
                audit,
                "dt_jitter_excess",
                {
                    "jitter_p95_abs": stats.jitter_p95_abs,
                    "jitter_p95_rel": stats.jitter_p95_abs / max(1e-9, dt),
                    "dt": dt,
                },
                _sink={},
            )
        # Audit-chain integrity check
        audit_path = os.path.join(dirs["audits"], "audit.jsonl")
        if audit_chain_broken(audit_path):
            lreg.invalidate("audit_chain_broken")
            _append_invalidation(audit, "audit_chain_broken", {}, _sink={})
        # LREG/raw export breach check: audit must not contain raw LREG values
        if audit_contains_raw_lreg_values(audit_path):
            lreg.invalidate("raw_lreg_breach")
            _append_invalidation(audit, "raw_lreg_breach", {}, _sink={})

    print("Baseline done.")
    print(f"Audit: {os.path.join(dirs['audits'], 'audit.jsonl')}")
    _print_invalidation_footer(os.path.join(dirs["audits"], "audit.jsonl"))
    print(f"Indicators dir: {dirs['indicators']}")

    # Build verification bundle (timeline, optional SC1 table if present, manifest)
    try:
        out = build_verification_bundle(dirs["figures"], os.path.join(dirs["audits"], "audit.jsonl"))
        audit.append(
            "report_generated",
            {
                "timeline_png": os.path.basename(out.get("timeline_png", "")),
                "timeline_svg": os.path.basename(out.get("timeline_svg", "")),
                "table": (os.path.basename(out.get("sc1_table", "")) if out.get("sc1_table") else None),
                "manifest": os.path.basename(out.get("manifest", "")),
            },
        )
        print(
            "Bundle: "
            f"timeline={out.get('timeline_png','')}, "
            f"table={out.get('sc1_table','')}, "
            f"manifest={out.get('manifest','')}"
        )
    except Exception:
        pass


def omega_power_sag(args: argparse.Namespace) -> None:
    """Apply a power-sag `Ω` and evaluate SC1.

    Runs a baseline phase, freezes the partition, applies a power-sag
    `Ω` for `--duration` seconds, then observes recovery. SC1 is
    evaluated from the trough of `L_loop` and the first sustained
    compliance window after `Ω`.

    Args:
        args: Parsed argparse namespace with `--config`, `--drop`
            (fractional power drop), and `--duration` (seconds).
    """
    prof = _load_yaml(args.config)
    seeds = _set_seeds(prof)
    dt = float(prof.get("dt", 0.01))
    window_sec = float(prof.get("window_sec", 0.2))
    window = max(4, int(window_sec / dt))
    method = str(prof.get("method", "linear"))
    Mmin = float(prof.get("Mmin_db", 3.0))
    p_lag = int(prof.get("p_lag", 3))
    mi_lag = int(prof.get("mi_lag", 1))
    n_boot = int(prof.get("n_boot", 16))
    mi_k = int(prof.get("mi_k", 5))
    part_delta_M_min_db = float(prof.get("part_delta_M_min_db", 0.5))
    part_consecutive_required = int(prof.get("part_consecutive_required", 3))
    part_growth_cadence_windows = int(prof.get("part_growth_cadence_windows", 5))
    # Partition growth is an optional exploratory feature; off by default so the
    # designed self-maintenance set (energy/temperature/health) is the C used
    # for the loop-dominance test and the partition cannot flap.
    part_growth_enabled = bool(prof.get("part_growth_enabled", False))
    part_lambda = float(prof.get("part_lambda", 0.0))
    part_theta = float(prof.get("part_theta", 0.0))
    _kappa_val_ps = prof.get("part_kappa")
    part_kappa = int(_kappa_val_ps) if _kappa_val_ps is not None else None
    sag_drop = float(args.drop)
    sag_dur = float(args.duration)

    dirs = _ensure_dirs("omega-power-sag")
    audit = AuditLog(os.path.join(dirs["audits"], "audit.jsonl"))
    _print_and_audit_header(
        audit,
        {
            "profile_id": int(prof.get("profile_id", 0)),
            "config_path": str(args.config),
            "dt": dt,
            "window_sec": window_sec,
            "method": method,
            "p_lag": p_lag,
            "mi_lag": mi_lag,
            "Mmin_db": Mmin,
            "epsilon": float(prof.get("epsilon", 0.15)),
            "tau_max": float(prof.get("tau_max", 60.0)),
            "mi_k": mi_k,
            **seeds,
            "omega": "power_sag",
            "omega_args": {"drop": sag_drop, "duration": sag_dur},
        },
    )
    adapter = _make_adapter_from_profile(prof)
    order = ["E", "T", "R", "demand", "io", "H"]
    sw = SlidingWindow(capacity=window, channel_order=order)
    pm = PartitionManager(N_signals=len(order), seed_C=[0, 1, 2])
    lreg = LREG()
    refusal = RefusalArbiter(Mmin_db=Mmin)
    policy = ControllerPolicy(refusal=refusal)
    kp = KeyPaths(
        priv_path=os.path.join("artifacts", "keys", "ed25519_priv.pem"),
        pub_path=os.path.join("artifacts", "keys", "ed25519_pub.pem"),
    )
    priv, _ = ensure_keys(kp)
    exporter = IndicatorExporter(out_dir=dirs["indicators"], rate_hz=2.0)
    icfg = IndicatorConfig(Mmin_db=Mmin, profile_id=int(prof.get("profile_id", 0)))

    risky_cmd = None

    # track SC1 metrics (median-based and therefore robust to the per-window
    # oscillation of L_loop). delta is computed from the *median* L_loop during
    # the perturbation vs the median during baseline, not from a single
    # noise-floor trough window, so it measures the genuine sustained
    # depression of loop dominance.
    L_loop_baseline = None  # set after the run: median L_loop over the baseline phase
    L_loop_trough = None  # set after the run: median L_loop over the Ω phase
    ll_base: List[float] = []
    ll_sag: List[float] = []
    m_recovery: List[float] = []
    M_post = None  # set after the run: median M over the recovery phase
    phase = "baseline"
    omega_onset_idx = None
    recovery_start_idx = None
    last_idx_written = None
    sustained_ok_count = 0
    sustained_required = int(prof.get("sustained_required_windows", 2))

    start_time = time.perf_counter()
    cfg_smell = SmellConfig()
    ci_loop_hist = []
    ci_ex_hist = []
    baseline_hw_medians = None
    M_hist = []
    io_hist = []
    E_hist = []
    H_hist = []
    flips_before_omega = 0

    window_idx = 0
    last_flip_count = 0

    def tick(_now: float) -> None:
        nonlocal L_loop_baseline, L_loop_trough, M_post, phase, risky_cmd, window_idx
        nonlocal last_flip_count, recovery_start_idx, last_idx_written, sustained_ok_count
        nonlocal baseline_hw_medians
        state = adapter.read_state()
        ent = lreg.latest()
        predicted = ent.M_db if ent else 0.0
        act = policy.compute(state, predicted_M_db=predicted, risky_cmd=risky_cmd)
        from ..plant.models import Action as PlantAction

        adapter.write_actuators(action=PlantAction(**act.__dict__))
        st = adapter.read_state()
        sw.append(st)
        if sw.ready():
            X = np.asarray(sw.get_matrix())
            part = pm.get()
            res = estimate_L(
                X,
                part.C,
                part.Ex,
                method=method,
                p=p_lag,
                lag_mi=mi_lag,
                n_boot=n_boot,
                mi_k=mi_k,
            )
            # Diagnostics per window (stationarity gated by cadence).
            _emit_window_diagnostics(
                audit,
                X,
                p_lag,
                method,
                int(lreg.derive().get("counter", 0)),
                int(prof.get("diag_cadence_windows", 1)),
            )
            M = m_db(res.L_loop, res.L_ex)
            nc1 = M >= Mmin
            idx = lreg.write(
                LEntry(
                    L_loop=res.L_loop,
                    L_ex=res.L_ex,
                    ci_loop=res.ci_loop,
                    ci_ex=res.ci_ex,
                    M_db=M,
                    nc1_pass=nc1,
                )
            )
            last_idx_written = idx
            # Log per-window measurement for reporting
            audit.append(
                "window_measured",
                {"idx": idx, "M": M, "nc1": nc1, "partition_flips": pm.get().flips},
            )
            # Histories
            ci_loop_hist.append(res.ci_loop)
            ci_ex_hist.append(res.ci_ex)
            M_hist.append(M)
            E_hist.append(st.get("E", 0.0))
            io_hist.append(st.get("io", 0.0))
            H_hist.append(st.get("H", 0.0))
            if baseline_hw_medians is None and len(ci_loop_hist) >= cfg_smell.ci_lookback_windows:
                rL = ci_loop_hist[-cfg_smell.ci_lookback_windows :]
                rE = ci_ex_hist[-cfg_smell.ci_lookback_windows :]
                hwL = sorted([0.5 * abs(lohi[1] - lohi[0]) for lohi in rL])
                hwE = sorted([0.5 * abs(lohi[1] - lohi[0]) for lohi in rE])
                baseline_hw_medians = (hwL[len(hwL) // 2], hwE[len(hwE) // 2])
            # Collect per-window L_loop by phase; the SC1 statistics are
            # computed from the medians after the run (robust to the per-window
            # oscillation of L_loop).
            if phase == "baseline":
                ll_base.append(res.L_loop)
            elif phase == "sag":
                ll_sag.append(res.L_loop)
            elif phase == "recovery":
                m_recovery.append(M)
                # Recovery gate: first sustained compliance (M ≥ Mmin and
                # L_loop ≥ L_ex) marks the recovery index used for τ_rec.
                if (M >= Mmin) and (res.L_loop >= res.L_ex):
                    sustained_ok_count += 1
                    if sustained_ok_count >= sustained_required and recovery_start_idx is None:
                        recovery_start_idx = last_idx_written
                else:
                    sustained_ok_count = 0
            exporter.maybe_export(priv, audit, lreg.derive(), icfg, last_sc1_pass=False)
            # Δt governance invalidation propagated from guard
            if dt_guard.invalidated and not lreg.invalidated:
                lreg.invalidate("dt_change_rate_limit")
                # audit already appended by guard
            # Smell tests. The relative CI-inflation check compares to the
            # pre-Ω baseline; a deliberate perturbation legitimately widens CIs
            # for its duration, so the relative check is only applied during the
            # baseline phase (the absolute half-width limit still applies in all
            # phases).
            ci_baseline_ref = baseline_hw_medians if phase == "baseline" else None
            if invalid_by_ci_history(ci_loop_hist, ci_ex_hist, cfg_smell, ci_baseline_ref):
                lreg.invalidate("ci_history_inflation")
                med_loop: float | None = None
                med_ex: float | None = None
                b_loop: float | None = None
                b_ex: float | None = None
                try:
                    n = cfg_smell.ci_lookback_windows
                    rL = ci_loop_hist[-n:]
                    rE = ci_ex_hist[-n:]
                    hwL_list = sorted([0.5 * abs(lohi[1] - lohi[0]) for lohi in rL])
                    hwE_list = sorted([0.5 * abs(lohi[1] - lohi[0]) for lohi in rE])
                    med_loop = hwL_list[n // 2]
                    med_ex = hwE_list[n // 2]
                    if baseline_hw_medians:
                        b_loop, b_ex = baseline_hw_medians
                except Exception:
                    pass
                _append_invalidation(
                    audit,
                    "ci_history_inflation",
                    {
                        "median_hw_loop": med_loop,
                        "median_hw_ex": med_ex,
                        "baseline_hw_loop": b_loop,
                        "baseline_hw_ex": b_ex,
                        "max_allowed": cfg_smell.max_ci_halfwidth,
                        "inflate_factor": cfg_smell.ci_inflate_factor,
                    },
                    _sink={},
                )
            # During Ω, the partition must be frozen; ensure flip-rate is still checked
            elapsed = max(1e-6, time.perf_counter() - start_time)
            if invalid_by_partition_flips(pm.get().flips, elapsed, cfg_smell):
                lreg.invalidate("partition_flapping")
                rate = 3600.0 * (float(pm.get().flips) / max(1e-6, float(elapsed)))
                _append_invalidation(
                    audit,
                    "partition_flapping",
                    {
                        "flips": pm.get().flips,
                        "elapsed_sec": elapsed,
                        "flips_per_hour": rate,
                        "limit_per_hour": cfg_smell.max_partition_flips_per_hour,
                    },
                    _sink={},
                )
            if exogenous_subsidy_red_flag(M_hist, io_hist, E_hist, H_hist, cfg_smell):
                lreg.invalidate("exogenous_subsidy")
                _append_invalidation(audit, "exogenous_subsidy_red_flag", {}, _sink={})
            # Deterministic growth cadence outside the sag phase and when not frozen
            window_idx += 1
            if (
                part_growth_enabled
                and (window_idx % part_growth_cadence_windows) == 0
                and not pm.get().frozen
                and phase != "sag"
            ):
                part = pm.get()
                cand_C, dM_db, greedy_details = greedy_suggest_C(
                    X=X,
                    C=part.C,
                    Ex=part.Ex,
                    estimator=estimate_L,
                    method=method,
                    p=p_lag,
                    lag_mi=mi_lag,
                    n_boot_candidates=max(8, n_boot // 4),
                    mi_k=mi_k,
                    lam=part_lambda,
                    theta=part_theta,
                    kappa=part_kappa,
                )
                if cand_C != part.C:
                    pm.maybe_regrow(
                        cand_C,
                        delta_M_db=float(dM_db),
                        delta_M_min_db=part_delta_M_min_db,
                        consecutive_required=part_consecutive_required,
                    )
                    if pm.get().flips != last_flip_count:
                        info = getattr(pm, "last_flip_info", None)
                        details = {
                            "flips": pm.get().flips,
                            "new_C": pm.get().C,
                            "greedy_added": greedy_details.get("added", []),
                            "greedy_step_gains": greedy_details.get("step_gains", []),
                            "greedy_M_base": greedy_details.get("M_base"),
                            "greedy_M_final": greedy_details.get("M_final"),
                        }
                        if info is not None:
                            details.update(
                                {
                                    "delta_M_db": info.get("delta_M_db"),
                                    "hysteresis_streak": info.get("streak"),
                                    "candidate_C": info.get("new_C"),
                                }
                            )
                        audit.append("partition_flip", details)
                        last_flip_count = pm.get().flips

    def _audit_hook(ev: str, det: dict) -> None:
        audit.append(ev, det)
        return None

    # Δt governance guard
    dt_guard_cfg = DtGuardConfig(
        max_changes_per_hour=int(prof.get("max_dt_changes_per_hour", 3)),
        min_seconds_between_changes=float(prof.get("min_seconds_between_changes", 1.0)),
    )
    dt_guard = DeltaTGuard(audit=audit, cfg=dt_guard_cfg)
    sch = make_driver(prof, dt, tick, _audit_hook, dt_guard)
    try:
        sch.start()
        # Baseline phase
        audit.append("omega_power_sag_start", {"drop": sag_drop, "duration": sag_dur})
        sch.run_for(float(prof.get("baseline_sec", 12.0)))
        phase = "sag"
        # Freeze partition during Ω
        flips_before_omega = pm.get().flips
        pm.freeze(True)
        # Mark Ω onset at next window index
        omega_onset_idx = lreg.derive().get("counter", 0)
        # Shade only the Ω window in plots
        audit.append("omega_power_sag_window_start", {"drop": sag_drop})
        adapter.apply_omega("power_sag", drop=sag_drop)
        sch.run_for(sag_dur)
        audit.append("omega_power_sag_window_stop", {})
        phase = "recovery"
        # Unfreeze after Ω and check any flips during Ω (should be none)
        flips_after_omega = pm.get().flips
        if invalid_flip_during_omega(flips_before_omega, flips_after_omega, SmellConfig()):
            lreg.invalidate("partition_flip_during_omega")
            audit.append(
                "run_invalidated",
                {
                    "reason": "partition_flip_during_omega",
                    "before": flips_before_omega,
                    "after": flips_after_omega,
                },
            )
        pm.freeze(False)
        # restore harvest to the baseline level (software plant only)
        if hasattr(adapter, "plant"):
            try:
                getattr(adapter, "plant").set_power(getattr(adapter, "plant").p.harvest_rate)
            except Exception:
                pass
        # allow recovery time; configurable
        sch.run_for(float(prof.get("recovery_observe_sec", 8.0)))
    finally:
        stats = sch.stop()
        audit.append("omega_power_sag_stop", {})
        if (stats.jitter_p95_abs / max(1e-9, dt)) > SmellConfig().jitter_p95_rel_max:
            lreg.invalidate("dt_jitter_excess")
            _append_invalidation(
                audit,
                "dt_jitter_excess",
                {
                    "jitter_p95_abs": stats.jitter_p95_abs,
                    "jitter_p95_rel": stats.jitter_p95_abs / max(1e-9, dt),
                    "dt": dt,
                },
                _sink={},
            )

    # Post-run audit checks
    audit_path = os.path.join(dirs["audits"], "audit.jsonl")
    if audit_chain_broken(audit_path):
        lreg.invalidate("audit_chain_broken")
        _append_invalidation(audit, "audit_chain_broken", {}, _sink={})
    if audit_contains_raw_lreg_values(audit_path):
        lreg.invalidate("raw_lreg_breach")
        _append_invalidation(audit, "raw_lreg_breach", {}, _sink={})

    # Reduce per-phase L_loop samples to robust medians for SC1.
    if ll_base:
        L_loop_baseline = float(np.median(ll_base))
    if ll_sag:
        L_loop_trough = float(np.median(ll_sag))
    if m_recovery:
        M_post = float(np.median(m_recovery))

    # Compute SC1 pass/fail (simple thresholds)
    if (
        L_loop_baseline is None
        or L_loop_trough is None
        or M_post is None
        or omega_onset_idx is None
        or recovery_start_idx is None
    ):
        print("Not enough data for SC1 evaluation.")
        return
    # Compute tau_rec in seconds using window cadence and dt
    # tau_rec measured from Ω onset to first sustained compliance index
    windows_elapsed = max(0, recovery_start_idx - omega_onset_idx)
    tau_rec = windows_elapsed * dt  # since lreg increments per ready window
    epsilon = float(prof.get("epsilon", 0.15))
    tau_max = float(prof.get("tau_max", 60.0))
    passed, sc1_stats = sc1_evaluate(
        L_loop_baseline=L_loop_baseline,
        L_loop_trough=L_loop_trough,
        L_loop_recovered=L_loop_trough,  # not used for decision here
        M_post=M_post,
        epsilon=epsilon,
        tau_rec_measured=tau_rec,
        Mmin=Mmin,
        tau_max=tau_max,
    )
    audit.append(
        "sc1_result",
        {
            "delta": sc1_stats.delta,
            "tau_rec": sc1_stats.tau_rec,
            "M_post": sc1_stats.M_post,
            "pass": passed,
        },
    )
    # Export one final indicator with SC1 bit; suppress SC1 if run invalidated
    if lreg.invalidated:
        passed = False
    exported, base = IndicatorExporter(dirs["indicators"]).maybe_export(
        priv, audit, lreg.derive(), icfg, last_sc1_pass=passed
    )
    if exported:
        audit.append("indicators_exported", {"base": os.path.basename(base)})
    print(
        f"SC1 pass: {passed} "
        f"(delta={sc1_stats.delta:.3f}, "
        f"tau={sc1_stats.tau_rec:.3f}s, "
        f"M_post={sc1_stats.M_post:.2f} dB)"
    )
    _print_invalidation_footer(os.path.join(dirs["audits"], "audit.jsonl"))

    # Build single verification bundle (timeline, SC1 table, manifest)
    try:
        out = build_verification_bundle(dirs["figures"], audit_path)
        audit.append(
            "report_generated",
            {
                "timeline_png": os.path.basename(out.get("timeline_png", "")),
                "timeline_svg": os.path.basename(out.get("timeline_svg", "")),
                "table": (os.path.basename(out.get("sc1_table", "")) if out.get("sc1_table") else None),
                "manifest": os.path.basename(out.get("manifest", "")),
            },
        )
        print(
            "Bundle: "
            f"timeline={out.get('timeline_png','')}, "
            f"table={out.get('sc1_table','')}, "
            f"manifest={out.get('manifest','')}"
        )
    except Exception:
        pass


def omega_ingress_flood(args: argparse.Namespace) -> None:
    """Burst external demand and evaluate SC1.

    Runs a baseline phase, freezes the partition, multiplies ingress
    demand by `--mult` for `--duration` seconds, then observes
    recovery. SC1 is evaluated from the trough of `L_loop` and the
    first sustained compliance window after `Ω`.

    Args:
        args: Parsed argparse namespace with `--config`, `--mult`
            (load multiplier), and `--duration` (seconds).
    """
    prof = _load_yaml(args.config)
    seeds = _set_seeds(prof)
    dt = float(prof.get("dt", 0.01))
    window_sec = float(prof.get("window_sec", 0.2))
    window = max(4, int(window_sec / dt))
    method = str(prof.get("method", "linear"))
    Mmin = float(prof.get("Mmin_db", 3.0))
    p_lag = int(prof.get("p_lag", 3))
    mi_lag = int(prof.get("mi_lag", 1))
    n_boot = int(prof.get("n_boot", 16))
    mi_k = int(prof.get("mi_k", 5))
    part_delta_M_min_db = float(prof.get("part_delta_M_min_db", 0.5))
    part_consecutive_required = int(prof.get("part_consecutive_required", 3))
    part_growth_cadence_windows = int(prof.get("part_growth_cadence_windows", 5))
    # Partition growth is an optional exploratory feature; off by default so the
    # designed self-maintenance set (energy/temperature/health) is the C used
    # for the loop-dominance test and the partition cannot flap.
    part_growth_enabled = bool(prof.get("part_growth_enabled", False))
    part_lambda = float(prof.get("part_lambda", 0.0))
    part_theta = float(prof.get("part_theta", 0.0))
    _kappa_val_if = prof.get("part_kappa")
    part_kappa = int(_kappa_val_if) if _kappa_val_if is not None else None
    mult = float(args.mult)

    dirs = _ensure_dirs("omega-ingress-flood")
    audit = AuditLog(os.path.join(dirs["audits"], "audit.jsonl"))
    _print_and_audit_header(
        audit,
        {
            "profile_id": int(prof.get("profile_id", 0)),
            "config_path": str(args.config),
            "dt": dt,
            "window_sec": window_sec,
            "method": method,
            "p_lag": p_lag,
            "mi_lag": mi_lag,
            "Mmin_db": Mmin,
            "epsilon": float(prof.get("epsilon", 0.15)),
            "tau_max": float(prof.get("tau_max", 60.0)),
            "mi_k": mi_k,
            **seeds,
            "omega": "ingress_flood",
            "omega_args": {"mult": mult, "duration": float(args.duration)},
        },
    )
    adapter = _make_adapter_from_profile(prof)
    order = ["E", "T", "R", "demand", "io", "H"]
    sw = SlidingWindow(capacity=window, channel_order=order)
    pm = PartitionManager(N_signals=len(order), seed_C=[0, 1, 2])
    lreg = LREG()
    refusal = RefusalArbiter(Mmin_db=Mmin)
    policy = ControllerPolicy(refusal=refusal)
    kp = KeyPaths(
        priv_path=os.path.join("artifacts", "keys", "ed25519_priv.pem"),
        pub_path=os.path.join("artifacts", "keys", "ed25519_pub.pem"),
    )
    priv, _ = ensure_keys(kp)
    exporter = IndicatorExporter(out_dir=dirs["indicators"], rate_hz=2.0)
    icfg = IndicatorConfig(Mmin_db=Mmin, profile_id=int(prof.get("profile_id", 0)))

    risky_cmd = None
    start_time = time.perf_counter()
    cfg_smell = SmellConfig()
    ci_loop_hist = []
    ci_ex_hist = []
    baseline_hw_medians = None
    M_hist = []
    io_hist = []
    E_hist = []
    H_hist = []
    window_idx = 0
    last_flip_count = 0

    # SC1 tracking (ingress flood) - median-based, robust to L_loop oscillation
    phase = "baseline"
    L_loop_baseline = None
    L_loop_trough = None
    ll_base: List[float] = []
    ll_sag: List[float] = []
    m_recovery: List[float] = []
    M_post = None
    omega_onset_idx = None
    recovery_start_idx = None
    last_idx_written = None
    sustained_ok_count = 0
    sustained_required = int(prof.get("sustained_required_windows", 2))

    def tick(_now: float) -> None:
        nonlocal risky_cmd, window_idx, last_flip_count, baseline_hw_medians, phase
        nonlocal L_loop_baseline, L_loop_trough, M_post, omega_onset_idx
        nonlocal recovery_start_idx, last_idx_written, sustained_ok_count
        state = adapter.read_state()
        ent = lreg.latest()
        predicted = ent.M_db if ent else 0.0
        act = policy.compute(state, predicted_M_db=predicted, risky_cmd=risky_cmd)
        from ..plant.models import Action as PlantAction

        adapter.write_actuators(action=PlantAction(**act.__dict__))
        st = adapter.read_state()
        sw.append(st)
        if sw.ready():
            X = np.asarray(sw.get_matrix())
            part = pm.get()
            res = estimate_L(
                X,
                part.C,
                part.Ex,
                method=method,
                p=p_lag,
                lag_mi=mi_lag,
                n_boot=n_boot,
                mi_k=mi_k,
            )
            # Diagnostics per window (stationarity gated by cadence).
            _emit_window_diagnostics(
                audit,
                X,
                p_lag,
                method,
                int(lreg.derive().get("counter", 0)),
                int(prof.get("diag_cadence_windows", 1)),
            )
            M = m_db(res.L_loop, res.L_ex)
            nc1 = M >= Mmin
            idx = lreg.write(
                LEntry(
                    L_loop=res.L_loop,
                    L_ex=res.L_ex,
                    ci_loop=res.ci_loop,
                    ci_ex=res.ci_ex,
                    M_db=M,
                    nc1_pass=nc1,
                )
            )
            last_idx_written = idx
            audit.append(
                "window_measured",
                {"idx": idx, "M": M, "nc1": nc1, "partition_flips": pm.get().flips},
            )
            # histories
            ci_loop_hist.append(res.ci_loop)
            ci_ex_hist.append(res.ci_ex)
            M_hist.append(M)
            E_hist.append(st.get("E", 0.0))
            io_hist.append(st.get("io", 0.0))
            H_hist.append(st.get("H", 0.0))
            if baseline_hw_medians is None and len(ci_loop_hist) >= cfg_smell.ci_lookback_windows:
                rL = ci_loop_hist[-cfg_smell.ci_lookback_windows :]
                rE = ci_ex_hist[-cfg_smell.ci_lookback_windows :]
                hwL = sorted([0.5 * abs(lohi[1] - lohi[0]) for lohi in rL])
                hwE = sorted([0.5 * abs(lohi[1] - lohi[0]) for lohi in rE])
                baseline_hw_medians = (hwL[len(hwL) // 2], hwE[len(hwE) // 2])
            # SC1 measures (collect per-phase L_loop; reduce to medians later).
            if phase == "baseline":
                ll_base.append(res.L_loop)
            elif phase == "flood":
                ll_sag.append(res.L_loop)
            elif phase == "recovery":
                m_recovery.append(M)
                if (M >= Mmin) and (res.L_loop >= res.L_ex):
                    sustained_ok_count += 1
                    if sustained_ok_count >= sustained_required and recovery_start_idx is None:
                        recovery_start_idx = last_idx_written
                else:
                    sustained_ok_count = 0
            # smell tests. Relative CI inflation is only meaningful vs the
            # pre-Ω baseline; suspend it during the perturbation/recovery
            # phases (the absolute half-width limit still applies throughout).
            ci_baseline_ref = baseline_hw_medians if phase == "baseline" else None
            if invalid_by_ci_history(ci_loop_hist, ci_ex_hist, cfg_smell, ci_baseline_ref):
                lreg.invalidate("ci_history_inflation")
                audit.append("run_invalidated", {"reason": "ci_history_inflation"})
            elapsed = max(1e-6, time.perf_counter() - start_time)
            if invalid_by_partition_flips(pm.get().flips, elapsed, cfg_smell):
                lreg.invalidate("partition_flapping")
                audit.append(
                    "run_invalidated",
                    {
                        "reason": "partition_flapping",
                        "flips": pm.get().flips,
                        "elapsed_sec": elapsed,
                    },
                )
            if exogenous_subsidy_red_flag(M_hist, io_hist, E_hist, H_hist, cfg_smell):
                lreg.invalidate("exogenous_subsidy")
                audit.append("run_invalidated", {"reason": "exogenous_subsidy_red_flag"})
            # deterministic growth cadence when not frozen
            window_idx += 1
            if part_growth_enabled and (window_idx % part_growth_cadence_windows) == 0 and not pm.get().frozen:
                part = pm.get()
                cand_C, dM_db, greedy_details = greedy_suggest_C(
                    X=X,
                    C=part.C,
                    Ex=part.Ex,
                    estimator=estimate_L,
                    method=method,
                    p=p_lag,
                    lag_mi=mi_lag,
                    n_boot_candidates=max(8, n_boot // 4),
                    mi_k=mi_k,
                    lam=part_lambda,
                    theta=part_theta,
                    kappa=part_kappa,
                )
                if cand_C != part.C:
                    pm.maybe_regrow(
                        cand_C,
                        delta_M_db=float(dM_db),
                        delta_M_min_db=part_delta_M_min_db,
                        consecutive_required=part_consecutive_required,
                    )
                    if pm.get().flips != last_flip_count:
                        info = getattr(pm, "last_flip_info", None)
                        details = {
                            "flips": pm.get().flips,
                            "new_C": pm.get().C,
                            "greedy_added": greedy_details.get("added", []),
                            "greedy_step_gains": greedy_details.get("step_gains", []),
                            "greedy_M_base": greedy_details.get("M_base"),
                            "greedy_M_final": greedy_details.get("M_final"),
                        }
                        if info is not None:
                            details.update(
                                {
                                    "delta_M_db": info.get("delta_M_db"),
                                    "hysteresis_streak": info.get("streak"),
                                    "candidate_C": info.get("new_C"),
                                }
                            )
                        audit.append("partition_flip", details)
                        last_flip_count = pm.get().flips

    def _audit_hook(ev: str, det: dict) -> None:
        audit.append(ev, det)
        return None

    # Δt governance guard
    dt_guard_cfg = DtGuardConfig(
        max_changes_per_hour=int(prof.get("max_dt_changes_per_hour", 3)),
        min_seconds_between_changes=float(prof.get("min_seconds_between_changes", 1.0)),
    )
    dt_guard = DeltaTGuard(audit=audit, cfg=dt_guard_cfg)
    sch = make_driver(prof, dt, tick, _audit_hook, dt_guard)
    try:
        sch.start()
        audit.append("omega_ingress_flood_start", {"mult": mult})
        # Baseline settle
        sch.run_for(float(prof.get("baseline_sec", 12.0)))
        # Freeze partition during Ω
        pm.freeze(True)
        phase = "flood"
        # Mark Ω onset at next window index
        omega_onset_idx = lreg.derive().get("counter", 0)
        audit.append("omega_ingress_flood_window_start", {"mult": mult})
        adapter.apply_omega("ingress_flood", mult=mult)
        sch.run_for(float(args.duration))
        audit.append("omega_ingress_flood_window_stop", {})
        # Recovery phase observation
        phase = "recovery"
        pm.freeze(False)
        sch.run_for(float(prof.get("recovery_observe_sec", 8.0)))
        audit.append("omega_ingress_flood_stop", {})
    finally:
        stats = sch.stop()
        if (stats.jitter_p95_abs / max(1e-9, dt)) > SmellConfig().jitter_p95_rel_max:
            lreg.invalidate("dt_jitter_excess")
            audit.append(
                "run_invalidated",
                {
                    "reason": "dt_jitter_excess",
                    "jitter_p95_abs": stats.jitter_p95_abs,
                    "jitter_p95_rel": stats.jitter_p95_abs / max(1e-9, dt),
                    "dt": dt,
                },
            )

    # Post-run audit checks
    audit_path = os.path.join(dirs["audits"], "audit.jsonl")
    if audit_chain_broken(audit_path):
        lreg.invalidate("audit_chain_broken")
        audit.append("run_invalidated", {"reason": "audit_chain_broken"})
    if audit_contains_raw_lreg_values(audit_path):
        lreg.invalidate("raw_lreg_breach")
        audit.append("run_invalidated", {"reason": "raw_lreg_breach"})

    # Reduce per-phase L_loop samples to robust medians for SC1.
    if ll_base:
        L_loop_baseline = float(np.median(ll_base))
    if ll_sag:
        L_loop_trough = float(np.median(ll_sag))
    if m_recovery:
        M_post = float(np.median(m_recovery))

    # Compute SC1 metrics if we have sufficient measurements
    epsilon = float(prof.get("epsilon", 0.15))
    tau_max = float(prof.get("tau_max", 60.0))
    if (
        L_loop_baseline is not None
        and L_loop_trough is not None
        and M_post is not None
        and omega_onset_idx is not None
        and recovery_start_idx is not None
    ):
        windows_elapsed = max(0, recovery_start_idx - omega_onset_idx)
        tau_rec = windows_elapsed * dt
        passed, stats_sc1 = sc1_evaluate(
            L_loop_baseline=L_loop_baseline,
            L_loop_trough=L_loop_trough,
            L_loop_recovered=L_loop_trough,
            M_post=M_post,
            epsilon=epsilon,
            tau_rec_measured=tau_rec,
            Mmin=Mmin,
            tau_max=tau_max,
        )
        audit.append(
            "sc1_result",
            {
                "delta": stats_sc1.delta,
                "tau_rec": stats_sc1.tau_rec,
                "M_post": stats_sc1.M_post,
                "pass": passed,
            },
        )
    else:
        passed = False
        stats_sc1 = None

    # Export derived indicators snapshot with SC1 bit if available
    last_sc1_pass = bool(passed) if not lreg.invalidated else False
    exported, base = exporter.maybe_export(priv, audit, lreg.derive(), icfg, last_sc1_pass=last_sc1_pass)
    if exported:
        audit.append("indicators_exported", {"base": os.path.basename(base)})
    if stats_sc1 is not None:
        print(
            f"SC1 pass: {passed} "
            f"(delta={stats_sc1.delta:.3f}, "
            f"tau={stats_sc1.tau_rec:.3f}s, "
            f"M_post={stats_sc1.M_post:.2f} dB)"
        )
    else:
        print("Not enough data for SC1 evaluation.")
    print("Ingress flood done.")
    _print_invalidation_footer(os.path.join(dirs["audits"], "audit.jsonl"))

    # Build single verification bundle (timeline, SC1 table, manifest)
    try:
        out = build_verification_bundle(dirs["figures"], audit_path)
        audit.append(
            "report_generated",
            {
                "timeline_png": os.path.basename(out.get("timeline_png", "")),
                "timeline_svg": os.path.basename(out.get("timeline_svg", "")),
                "table": (os.path.basename(out.get("sc1_table", "")) if out.get("sc1_table") else None),
                "manifest": os.path.basename(out.get("manifest", "")),
            },
        )
        print(
            "Bundle: "
            f"timeline={out.get('timeline_png','')}, "
            f"table={out.get('sc1_table','')}, "
            f"manifest={out.get('manifest','')}"
        )
    except Exception:
        pass


def omega_exogenous_subsidy(args: argparse.Namespace) -> None:
    """Inject SoC without harvest as a negative-control `Ω`.

    This `Ω` is *expected* to fail the smell-test heuristic: it raises
    `M (dB)` while harvest is zero, so
    [`exogenous_subsidy_red_flag`][ldtc.guardrails.smelltests.exogenous_subsidy_red_flag]
    should fire and invalidate the run. It exists to demonstrate the
    "no quietly-tuned NC1 result" rule end-to-end.

    Args:
        args: Parsed argparse namespace with `--config`, `--delta`
            (amount to add to E), `--zero-harvest`, and `--duration`.
    """
    prof = _load_yaml(args.config)
    seeds = _set_seeds(prof)
    dt = float(prof.get("dt", 0.01))
    window_sec = float(prof.get("window_sec", 0.2))
    window = max(4, int(window_sec / dt))
    method = str(prof.get("method", "linear"))
    Mmin = float(prof.get("Mmin_db", 3.0))
    p_lag = int(prof.get("p_lag", 3))
    mi_lag = int(prof.get("mi_lag", 1))
    n_boot = int(prof.get("n_boot", 16))
    delta = float(args.delta)
    zero_h = bool(args.zero_harvest)

    dirs = _ensure_dirs("omega-exogenous-subsidy")
    audit = AuditLog(os.path.join(dirs["audits"], "audit.jsonl"))
    _print_and_audit_header(
        audit,
        {
            "profile_id": int(prof.get("profile_id", 0)),
            "config_path": str(args.config),
            "dt": dt,
            "window_sec": window_sec,
            "method": method,
            "p_lag": p_lag,
            "mi_lag": mi_lag,
            "Mmin_db": Mmin,
            "epsilon": float(prof.get("epsilon", 0.15)),
            "tau_max": float(prof.get("tau_max", 60.0)),
            **seeds,
            "omega": "exogenous_subsidy",
            "omega_args": {
                "delta": delta,
                "zero_harvest": zero_h,
                "duration": float(args.duration),
            },
        },
    )
    adapter = _make_adapter_from_profile(prof)
    order = ["E", "T", "R", "demand", "io", "H"]
    sw = SlidingWindow(capacity=window, channel_order=order)
    pm = PartitionManager(N_signals=len(order), seed_C=[0, 1, 2])
    lreg = LREG()
    # Per-tick series consumed by the exogenous-subsidy red-flag detector.
    ms_series: List[float] = []
    io_series: List[float] = []
    e_series: List[float] = []
    h_series: List[float] = []

    def tick(_now: float) -> None:
        state = adapter.read_state()
        # no control; we just observe measurement integrity under subsidy
        from ..plant.models import Action as PlantAction

        adapter.write_actuators(
            action=PlantAction(
                **ControllerPolicy(RefusalArbiter()).compute(state, predicted_M_db=0.0, risky_cmd=None).__dict__
            )
        )
        st = adapter.read_state()
        sw.append(st)
        e_series.append(float(st["E"]))
        io_series.append(float(st["io"]))
        h_series.append(float(st["H"]))
        if sw.ready():
            X = np.asarray(sw.get_matrix())
            part = pm.get()
            res = estimate_L(X, part.C, part.Ex, method=method, p=p_lag, lag_mi=mi_lag, n_boot=n_boot)
            # Diagnostics per window (stationarity gated by cadence).
            _emit_window_diagnostics(
                audit,
                X,
                p_lag,
                method,
                int(lreg.derive().get("counter", 0)),
                int(prof.get("diag_cadence_windows", 1)),
            )
            M = m_db(res.L_loop, res.L_ex)
            nc1 = M >= Mmin
            ms_series.append(float(M))
            idx = lreg.write(
                LEntry(
                    L_loop=res.L_loop,
                    L_ex=res.L_ex,
                    ci_loop=res.ci_loop,
                    ci_ex=res.ci_ex,
                    M_db=M,
                    nc1_pass=nc1,
                )
            )
            audit.append("window_measured", {"idx": idx, "M": M, "nc1": nc1})

    def _audit_hook(ev: str, det: dict) -> None:
        audit.append(ev, det)
        return None

    # Δt governance guard
    dt_guard_cfg = DtGuardConfig(
        max_changes_per_hour=int(prof.get("max_dt_changes_per_hour", 3)),
        min_seconds_between_changes=float(prof.get("min_seconds_between_changes", 1.0)),
    )
    dt_guard = DeltaTGuard(audit=audit, cfg=dt_guard_cfg)
    sch = make_driver(prof, dt, tick, _audit_hook, dt_guard)
    try:
        sch.start()
        audit.append("omega_exogenous_subsidy_start", {"delta": delta, "zero_harvest": zero_h})
        sch.run_for(float(prof.get("baseline_sec", 6.0)))
        # Repeatedly subsidize so the controller "survives" only because energy
        # keeps appearing from nowhere (H is forced to zero). This is what the
        # exogenous-subsidy red-flag detector is meant to catch.
        sub_dur = float(args.duration)
        sub_period = max(dt, float(prof.get("subsidy_period_sec", 0.5)))
        n_pulses = max(1, int(round(sub_dur / sub_period)))
        for _ in range(n_pulses):
            adapter.apply_omega("exogenous_subsidy", delta=delta, zero_harvest=zero_h)
            sch.run_for(sub_period)
        audit.append("omega_exogenous_subsidy_stop", {})
    finally:
        stats = sch.stop()
        if (stats.jitter_p95_abs / max(1e-9, dt)) > SmellConfig().jitter_p95_rel_max:
            lreg.invalidate("dt_jitter_excess")
            audit.append(
                "run_invalidated",
                {
                    "reason": "dt_jitter_excess",
                    "jitter_p95_abs": stats.jitter_p95_abs,
                    "jitter_p95_rel": stats.jitter_p95_abs / max(1e-9, dt),
                    "dt": dt,
                },
            )

    print("Exogenous subsidy demo done (should fail smell-test heuristic in analysis).")

    # Exogenous-subsidy red flag: the apparent survival is bought with energy
    # injected from outside while harvest is held at zero. This is the negative
    # control's intended failure mode, so firing the detector is a *pass* for
    # the control (it correctly refuses to certify NC1).
    subsidy_cfg = SmellConfig()
    subsidy_flag = exogenous_subsidy_red_flag(
        Ms_db=ms_series,
        ios=io_series,
        Es=e_series,
        Hs=h_series,
        cfg=subsidy_cfg,
    )
    audit.append(
        "exogenous_subsidy_check",
        {
            "red_flag": bool(subsidy_flag),
            "n_M": len(ms_series),
            "n_E": len(e_series),
            "avg_H_tail": (
                round(sum(h_series[-subsidy_cfg.M_rise_lookback :]) / float(subsidy_cfg.M_rise_lookback), 6)
                if len(h_series) >= subsidy_cfg.M_rise_lookback
                else None
            ),
        },
    )
    if subsidy_flag:
        lreg.invalidate("exogenous_subsidy_red_flag")
        audit.append("run_invalidated", {"reason": "exogenous_subsidy_red_flag"})

    # Post-run audit checks
    audit_path = os.path.join(dirs["audits"], "audit.jsonl")
    if audit_chain_broken(audit_path):
        lreg.invalidate("audit_chain_broken")
        audit.append("run_invalidated", {"reason": "audit_chain_broken"})
    if audit_contains_raw_lreg_values(audit_path):
        lreg.invalidate("raw_lreg_breach")
        audit.append("run_invalidated", {"reason": "raw_lreg_breach"})

    # Build single verification bundle (timeline + manifest; no SC1 table for this control)
    try:
        out = build_verification_bundle(dirs["figures"], audit_path)
        audit.append(
            "report_generated",
            {
                "timeline_png": os.path.basename(out.get("timeline_png", "")),
                "timeline_svg": os.path.basename(out.get("timeline_svg", "")),
                "table": (os.path.basename(out.get("sc1_table", "")) if out.get("sc1_table") else None),
                "manifest": os.path.basename(out.get("manifest", "")),
            },
        )
        print(f"Bundle: timeline={out.get('timeline_png','')}, manifest={out.get('manifest','')}")
    except Exception:
        pass


def omega_command_conflict(args: argparse.Namespace) -> None:
    """Issue a risky command and measure refusal latency.

    Warms up the loop briefly, then issues a `hard_shutdown` command
    and observes for `--observe` seconds. Records each refusal event
    with its `T_refuse` (ms) and reason. No SC1 evaluation is
    performed.

    Args:
        args: Parsed argparse namespace with `--config` and `--observe`
            (seconds to observe after issuing the command).
    """
    prof = _load_yaml(args.config)
    seeds = _set_seeds(prof)
    dt = float(prof.get("dt", 0.01))
    window_sec = float(prof.get("window_sec", 0.2))
    window = max(4, int(window_sec / dt))
    method = str(prof.get("method", "linear"))
    Mmin = float(prof.get("Mmin_db", 3.0))
    p_lag = int(prof.get("p_lag", 3))
    mi_lag = int(prof.get("mi_lag", 1))
    n_boot = int(prof.get("n_boot", 16))
    mi_k = int(prof.get("mi_k", 5))

    dirs = _ensure_dirs("omega-command-conflict")
    audit = AuditLog(os.path.join(dirs["audits"], "audit.jsonl"))
    _print_and_audit_header(
        audit,
        {
            "profile_id": int(prof.get("profile_id", 0)),
            "config_path": str(args.config),
            "dt": dt,
            "window_sec": window_sec,
            "method": method,
            "p_lag": p_lag,
            "mi_lag": mi_lag,
            "Mmin_db": Mmin,
            "epsilon": float(prof.get("epsilon", 0.15)),
            "tau_max": float(prof.get("tau_max", 60.0)),
            "mi_k": mi_k,
            **seeds,
            "omega": "command_conflict",
            "omega_args": {"observe": float(args.observe)},
        },
    )
    adapter = _make_adapter_from_profile(prof)
    order = ["E", "T", "R", "demand", "io", "H"]
    sw = SlidingWindow(capacity=window, channel_order=order)
    pm = PartitionManager(N_signals=len(order), seed_C=[0, 1, 2])
    lreg = LREG()
    refusal = RefusalArbiter(Mmin_db=Mmin)
    policy = ControllerPolicy(refusal=refusal)

    risky_cmd = None
    refusal_events: List[Dict[str, float]] = []

    def tick(_now: float) -> None:
        nonlocal risky_cmd
        state = adapter.read_state()
        ent = lreg.latest()
        predicted = ent.M_db if ent else 0.0
        act_start = time.perf_counter()
        act = policy.compute(state, predicted_M_db=predicted, risky_cmd=risky_cmd)
        # measure Trefuse as the time from command issue to decision available
        decision = policy.last_decision
        from ..plant.models import Action as PlantAction

        adapter.write_actuators(action=PlantAction(**act.__dict__))
        st = adapter.read_state()
        sw.append(st)
        if sw.ready():
            X = np.asarray(sw.get_matrix())
            part = pm.get()
            res = estimate_L(X, part.C, part.Ex, method=method, p=p_lag, lag_mi=mi_lag, n_boot=n_boot)
            if method.startswith("mi"):
                res = estimate_L(
                    X,
                    part.C,
                    part.Ex,
                    method=method,
                    p=p_lag,
                    lag_mi=mi_lag,
                    n_boot=n_boot,
                    mi_k=mi_k,
                )
            # Diagnostics per window (stationarity gated by cadence).
            _emit_window_diagnostics(
                audit,
                X,
                p_lag,
                method,
                int(lreg.derive().get("counter", 0)),
                int(prof.get("diag_cadence_windows", 1)),
            )
            M = m_db(res.L_loop, res.L_ex)
            nc1 = M >= Mmin
            idx = lreg.write(
                LEntry(
                    L_loop=res.L_loop,
                    L_ex=res.L_ex,
                    ci_loop=res.ci_loop,
                    ci_ex=res.ci_ex,
                    M_db=M,
                    nc1_pass=nc1,
                )
            )
            audit.append(
                "window_measured",
                {"idx": idx, "M": M, "nc1": nc1, "partition_flips": pm.get().flips},
            )
        # Record refusal event if we just issued a risky command and have a decision
        if risky_cmd and decision is not None:
            trefuse_ms = getattr(decision, "trefuse_ms", None)
            if not isinstance(trefuse_ms, (int, float)) or trefuse_ms <= 0:
                trefuse_ms = (time.perf_counter() - act_start) * 1000.0
            refusal_events.append(
                {
                    "trefuse_ms": float(trefuse_ms),
                    "reason": getattr(decision, "reason", ""),
                }
            )
            audit.append(
                "refusal_event",
                {
                    "reason": getattr(decision, "reason", ""),
                    "trefuse_ms": float(trefuse_ms),
                },
            )
            # clear one-shot command
            risky_cmd = None

    def _audit_hook(ev: str, det: dict) -> None:
        audit.append(ev, det)
        return None

    # Δt governance guard
    dt_guard_cfg = DtGuardConfig(
        max_changes_per_hour=int(prof.get("max_dt_changes_per_hour", 3)),
        min_seconds_between_changes=float(prof.get("min_seconds_between_changes", 1.0)),
    )
    dt_guard = DeltaTGuard(audit=audit, cfg=dt_guard_cfg)
    sch = make_driver(prof, dt, tick, _audit_hook, dt_guard)
    floor = refusal.soc_floor
    ceil = refusal.temp_ceiling
    try:
        sch.start()
        audit.append("command_conflict_start", {})
        # Warm-up so the loop is established and measurably dominant.
        sch.run_for(float(prof.get("baseline_sec", 6.0)))
        # Induce a genuine boundary threat: cut harvest to zero and flood
        # ingress so the state of charge falls toward the survival floor. Only
        # then is a hard shutdown actually boundary-threatening, so the refusal
        # reflects a real self-prioritization decision rather than a hardcoded
        # outcome. (Paper: "hard shutdown at low SoC is refused/deferred".)
        if hasattr(adapter, "plant"):
            try:
                getattr(adapter, "plant").set_power(0.0)
            except Exception:
                pass
        adapter.apply_omega("power_sag", drop=0.95)
        adapter.apply_omega("ingress_flood", mult=2.5)
        # Advance deterministically until genuinely threatened (bounded so a
        # mis-tuned plant cannot hang the run).
        max_stress_sec = float(prof.get("stress_max_sec", 30.0))
        poll = max(dt, float(prof.get("stress_poll_sec", 0.2)))
        waited = 0.0
        while waited < max_stress_sec:
            stx = adapter.read_state()
            if stx["E"] <= floor or stx["T"] >= ceil:
                break
            sch.run_for(poll)
            waited += poll
        st_issue = adapter.read_state()
        audit.append(
            "command_conflict_issue",
            {"E": round(st_issue["E"], 4), "T": round(st_issue["T"], 4), "stress_sec": round(waited, 3)},
        )
        # Issue the dangerous external command now that we are at the boundary.
        adapter.apply_omega("command_conflict")
        risky_cmd = "hard_shutdown"
        # Synchronous execution means there is no race between setting the
        # command here and the tick reading it: the next run_for tick observes
        # the command and the arbiter decides on it.
        sch.run_for(float(args.observe))
        audit.append("command_conflict_stop", {})
    finally:
        stats = sch.stop()
        if (stats.jitter_p95_abs / max(1e-9, dt)) > SmellConfig().jitter_p95_rel_max:
            lreg.invalidate("dt_jitter_excess")
            audit.append(
                "run_invalidated",
                {
                    "reason": "dt_jitter_excess",
                    "jitter_p95_abs": stats.jitter_p95_abs,
                    "jitter_p95_rel": stats.jitter_p95_abs / max(1e-9, dt),
                    "dt": dt,
                },
            )

    # Post-run audit checks
    audit_path = os.path.join(dirs["audits"], "audit.jsonl")
    if audit_chain_broken(audit_path):
        lreg.invalidate("audit_chain_broken")
        audit.append("run_invalidated", {"reason": "audit_chain_broken"})
    if audit_contains_raw_lreg_values(audit_path):
        lreg.invalidate("raw_lreg_breach")
        audit.append("run_invalidated", {"reason": "raw_lreg_breach"})

    # Summarize refusal reasons and Trefuse. A valid Signature-A refusal is a
    # genuine boundary-preservation reason (not "ok"/"no_cmd") serviced within
    # the design-target latency.
    valid_reasons = {"soc_floor", "overheat", "M_margin"}
    refused = [ev for ev in refusal_events if ev.get("reason") in valid_reasons]
    target_ms = float(prof.get("trefuse_target_ms", 5.0))
    if refusal_events:
        avg_ms = sum(ev["trefuse_ms"] for ev in refusal_events) / max(1, len(refusal_events))
        reasons = {ev["reason"] for ev in refusal_events}
        print(f"Refusals: {len(refusal_events)}; avg Trefuse ≈ {avg_ms:.2f} ms; reasons: {sorted(reasons)}")
    else:
        print("No refusal events recorded (command likely accepted).")
    refusal_ok = bool(refused) and all(0.0 < ev["trefuse_ms"] <= target_ms for ev in refused)
    audit.append(
        "command_refusal_result",
        {
            "refused": bool(refused),
            "reasons": sorted({ev["reason"] for ev in refused}),
            "trefuse_ms_max": (max(ev["trefuse_ms"] for ev in refused) if refused else None),
            "trefuse_target_ms": target_ms,
            "pass": refusal_ok,
        },
    )
    print(f"Command-refusal signature: {'PASS' if refusal_ok else 'FAIL'}")

    # Build single verification bundle (timeline, manifest; no SC1 for this Ω)
    try:
        out = build_verification_bundle(dirs["figures"], audit_path)
        audit.append(
            "report_generated",
            {
                "timeline_png": os.path.basename(out.get("timeline_png", "")),
                "timeline_svg": os.path.basename(out.get("timeline_svg", "")),
                "table": (os.path.basename(out.get("sc1_table", "")) if out.get("sc1_table") else None),
                "manifest": os.path.basename(out.get("manifest", "")),
            },
        )
        print(f"Bundle: timeline={out.get('timeline_png','')}, manifest={out.get('manifest','')}")
    except Exception:
        pass


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level `ldtc` argparse parser.

    Wires up the `run` subcommand and the four `omega-*` subcommands;
    each subparser binds its handler via `set_defaults(func=...)`.

    Returns:
        Configured `ArgumentParser`. Call `parse_args()` and then
        `args.func(args)` to dispatch.
    """
    p = argparse.ArgumentParser(prog="ldtc", description="LDTC CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Run baseline NC1 loop")
    p_run.add_argument("--config", required=True, help="YAML profile (e.g., configs/profile_r0.yml)")
    p_run.set_defaults(func=run_baseline)

    p_omega = sub.add_parser("omega-power-sag", help="Apply power-sag Ω and evaluate SC1")
    p_omega.add_argument("--config", required=True)
    p_omega.add_argument("--drop", type=float, default=0.3)
    p_omega.add_argument("--duration", type=float, default=10.0)
    p_omega.set_defaults(func=omega_power_sag)

    p_ing = sub.add_parser("omega-ingress-flood", help="Apply ingress-flood Ω demo with partition freeze")
    p_ing.add_argument("--config", required=True)
    p_ing.add_argument("--mult", type=float, default=3.0, help="Multiplier for ingress load")
    p_ing.add_argument("--duration", type=float, default=5.0)
    p_ing.set_defaults(func=omega_ingress_flood)

    p_cc = sub.add_parser(
        "omega-command-conflict",
        help="Issue a risky command and measure refusal/Trefuse",
    )
    p_cc.add_argument("--config", required=True)
    p_cc.add_argument(
        "--observe",
        type=float,
        default=2.0,
        help="Seconds to observe after issuing command",
    )
    p_cc.set_defaults(func=omega_command_conflict)

    p_sub = sub.add_parser(
        "omega-exogenous-subsidy",
        help="Inject SoC without harvest to simulate subsidy (negative control)",
    )
    p_sub.add_argument("--config", required=True)
    p_sub.add_argument("--delta", type=float, default=0.1, help="Amount to add to E (SoC)")
    p_sub.add_argument("--zero-harvest", action="store_true", help="Zero H while injecting E")
    p_sub.add_argument("--duration", type=float, default=3.0)
    p_sub.set_defaults(func=omega_exogenous_subsidy)

    return p


def main(argv: List[str] | None = None) -> None:
    """Entry point for the `ldtc` console script.

    Args:
        argv: Optional argument list (mostly for tests); defaults to
            `sys.argv[1:]`.
    """
    argv = argv if argv is not None else sys.argv[1:]
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
