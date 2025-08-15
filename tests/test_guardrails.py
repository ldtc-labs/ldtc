from __future__ import annotations

from ldtc.guardrails.lreg import LREG, LEntry
from ldtc.guardrails.smelltests import (
    SmellConfig,
    invalid_by_partition_flips,
    invalid_flip_during_omega,
    flips_per_hour,
)
from ldtc.guardrails.audit import AuditLog
from ldtc.guardrails.dt_guard import DeltaTGuard, DtGuardConfig
from ldtc.guardrails.smelltests import (
    audit_chain_broken,
    audit_contains_raw_lreg_values,
)
from ldtc.runtime.scheduler import FixedScheduler
import time


def test_lreg_derive():
    lr = LREG()
    lr.write(LEntry(0.2, 0.1, (0.1, 0.3), (0.05, 0.2), M_db=3.0, nc1_pass=True))
    d = lr.derive()
    assert d["nc1"] is True
    assert d["counter"] == 1


def test_partition_flip_rate_invalidation():
    cfg = SmellConfig()
    # 3 flips in one hour exceeds default max_partition_flips_per_hour=2
    assert invalid_by_partition_flips(flips=3, elapsed_sec=3600.0, cfg=cfg) is True
    # 2 flips/hour is okay
    assert invalid_by_partition_flips(flips=2, elapsed_sec=3600.0, cfg=cfg) is False
    # Check computation utility
    fph = flips_per_hour(3, 3600.0)
    assert abs(fph - 3.0) < 1e-6


def test_flip_during_omega_invalidation():
    cfg = SmellConfig(forbid_partition_flip_during_omega=True)
    assert invalid_flip_during_omega(5, 6, cfg) is True
    assert invalid_flip_during_omega(5, 5, cfg) is False
    # If disabled, never invalidates
    cfg2 = SmellConfig(forbid_partition_flip_during_omega=False)
    assert invalid_flip_during_omega(1, 2, cfg2) is False


def test_dt_guard_rate_limited(tmp_path):
    audit_path = tmp_path / "audit.jsonl"
    audit = AuditLog(str(audit_path))
    cfg = DtGuardConfig(max_changes_per_hour=1, min_seconds_between_changes=10.0)
    guard = DeltaTGuard(audit=audit, cfg=cfg)

    class _DummyScheduler:
        def __init__(self):
            self.dt = 0.01

        def set_dt(self, new_dt: float) -> float:
            old = self.dt
            self.dt = new_dt
            return old

    sch = _DummyScheduler()
    ok1 = guard.change_dt(scheduler=sch, new_dt=0.02, policy_digest="abc")
    assert ok1 is True and sch.dt == 0.02
    # Immediate back-to-back should be refused and invalidate the run
    ok2 = guard.change_dt(scheduler=sch, new_dt=0.03, policy_digest="def")
    assert ok2 is False


def test_audit_chain_and_raw_lreg_detection(tmp_path):
    audit_path = tmp_path / "audit.jsonl"
    audit = AuditLog(str(audit_path))
    # two valid sequential entries
    audit.append("start", {})
    audit.append("tick", {})
    assert audit_chain_broken(str(audit_path)) is False
    # append a malformed (counter gap) record directly
    with open(audit_path, "a", encoding="utf-8") as f:
        f.write(
            '{"counter": 100, "ts": 0, "event": "bad", "details": {}, "prev_hash": "x", "hash": "y"}\n'
        )
    assert audit_chain_broken(str(audit_path)) is True
    # check raw LREG leakage detection
    audit2_path = tmp_path / "audit2.jsonl"
    with open(audit2_path, "w", encoding="utf-8") as f:
        f.write('{"counter":1,"ts":0,"event":"ok","details":{}}\n')
        f.write('{"counter":2,"ts":1,"event":"leak","details":{"L_loop":1.23}}\n')
    assert audit_contains_raw_lreg_values(str(audit2_path)) is True


def test_scheduler_jitter_p95_within_bounds(tmp_path):
    audit_path = tmp_path / "audit_jitter.jsonl"
    audit = AuditLog(str(audit_path))

    # No-op tick
    def _tick(_now: float) -> None:
        return None

    # Wire scheduler audit to AuditLog
    def _audit_hook(ev: str, det: dict) -> None:
        audit.append(ev, det)
        return None

    dt = 0.02  # 20 ms target to reduce relative jitter flakiness on CI
    sch = FixedScheduler(dt=dt, tick_fn=_tick, audit_hook=_audit_hook)
    sch.start()
    try:
        time.sleep(0.8)
    finally:
        stats = sch.stop()

    # Assert p95 relative jitter bound per smell config
    cfg = SmellConfig()
    assert stats.jitter_p95_abs >= 0.0
    assert (stats.jitter_p95_abs / dt) <= cfg.jitter_p95_rel_max

    # Also verify the audit captured the jitter fields
    found = False
    with open(audit_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            obj = __import__("json").loads(line)
            if obj.get("event") == "scheduler_stopped":
                det = obj.get("details", {}) or {}
                assert "jitter_p95_abs" in det and "jitter_p95_rel" in det
                found = True
    assert found is True


def test_dt_guard_refusal_is_audited(tmp_path):
    audit_path = tmp_path / "audit_dt.jsonl"
    audit = AuditLog(str(audit_path))
    cfg = DtGuardConfig(max_changes_per_hour=1, min_seconds_between_changes=10.0)
    guard = DeltaTGuard(audit=audit, cfg=cfg)

    class _DummyScheduler:
        def __init__(self):
            self.dt = 0.01

        def set_dt(self, new_dt: float) -> float:
            old = self.dt
            self.dt = new_dt
            return old

    sch = _DummyScheduler()
    ok1 = guard.change_dt(scheduler=sch, new_dt=0.02, policy_digest="abc")
    assert ok1 is True and sch.dt == 0.02

    # Back-to-back change should be refused and log run_invalidated
    ok2 = guard.change_dt(scheduler=sch, new_dt=0.03, policy_digest="def")
    assert ok2 is False

    # Audit must contain run_invalidated with reason dt_change_rate_limit
    saw_dt_changed = False
    saw_invalid = False
    import json

    with open(audit_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            obj = json.loads(line)
            if obj.get("event") == "dt_changed":
                saw_dt_changed = True
            if obj.get("event") == "run_invalidated":
                det = obj.get("details", {}) or {}
                if det.get("reason") == "dt_change_rate_limit":
                    saw_invalid = True
    assert saw_dt_changed is True
    assert saw_invalid is True
