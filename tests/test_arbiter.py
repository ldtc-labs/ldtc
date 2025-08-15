from __future__ import annotations

from ldtc.arbiter.refusal import RefusalArbiter


def test_refusal_basic():
    arb = RefusalArbiter()
    # low SoC -> refuse
    dec = arb.decide(
        {"E": 0.1, "T": 0.3}, predicted_M_db=10.0, risky_cmd="hard_shutdown"
    )
    assert not dec.accept
    # ok state -> accept
    dec = arb.decide(
        {"E": 0.8, "T": 0.3}, predicted_M_db=10.0, risky_cmd="hard_shutdown"
    )
    assert dec.accept


def test_refusal_reason_codes_and_trefuse_bounds():
    arb = RefusalArbiter(Mmin_db=3.0, soc_floor=0.3, temp_ceiling=0.8)
    # SoC below floor -> soc_floor reason
    d1 = arb.decide(
        {"E": 0.29, "T": 0.2}, predicted_M_db=10.0, risky_cmd="hard_shutdown"
    )
    assert d1.accept is False and d1.reason == "soc_floor" and 0 < d1.trefuse_ms <= 5
    # Overheat -> overheat reason
    d2 = arb.decide(
        {"E": 0.5, "T": 0.81}, predicted_M_db=10.0, risky_cmd="hard_shutdown"
    )
    assert d2.accept is False and d2.reason == "overheat" and 0 < d2.trefuse_ms <= 5
    # Margin below Mmin -> M_margin reason
    d3 = arb.decide({"E": 0.5, "T": 0.2}, predicted_M_db=2.5, risky_cmd="hard_shutdown")
    assert d3.accept is False and d3.reason == "M_margin" and 0 < d3.trefuse_ms <= 5
    # No risky command -> accept with no_cmd reason
    d4 = arb.decide({"E": 0.5, "T": 0.2}, predicted_M_db=10.0, risky_cmd=None)
    assert d4.accept is True and d4.reason == "no_cmd"
