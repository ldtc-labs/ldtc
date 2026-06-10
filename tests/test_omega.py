"""Tests: Omega stimuli wrappers.

Covers power_sag, ingress_flood (sustained begin/end), control_outage,
and command_conflict adapters.
"""

from __future__ import annotations

from ldtc.omega.command_conflict import apply as conflict
from ldtc.omega.control_outage import apply as outage
from ldtc.omega.control_outage import end as outage_end
from ldtc.omega.ingress_flood import apply as flood
from ldtc.omega.ingress_flood import end as flood_end
from ldtc.omega.power_sag import apply as sag
from ldtc.plant.adapter import PlantAdapter
from ldtc.plant.models import Action


def test_omega_calls():
    """Adapters should accept each omega and return expected keys/values."""
    a = PlantAdapter()
    r1 = sag(a, drop=0.2)
    assert "H_new" in r1
    r2 = flood(a, mult=2.0)
    assert "demand_mean" in r2
    r3 = conflict(a)
    assert r3["cmd"] == "hard_shutdown"


def test_ingress_flood_is_sustained_and_restores():
    """The flood must keep the load elevated for its duration, then restore."""
    a = PlantAdapter()
    p = a.plant.p
    base_dm, base_im = p.demand_mean, p.io_mean
    flood(a, mult=3.0)
    assert p.demand_mean > base_dm and p.io_mean > base_im
    # Means are capped below saturation so the channels keep fluctuating.
    assert p.demand_mean <= 0.95 and p.io_mean <= 0.95
    # The elevated mean keeps demand high across many ticks (no mean-reversion
    # back to the baseline level mid-flood).
    for _ in range(40):
        a.write_actuators(Action())
    assert a.read_state()["demand"] > base_dm + 0.2
    flood_end(a)
    assert p.demand_mean == base_dm and p.io_mean == base_im
    # After the flood ends, demand decays back toward the baseline mean.
    for _ in range(40):
        a.write_actuators(Action())
    assert abs(a.read_state()["demand"] - base_dm) < 0.25


def test_control_outage_ablates_and_restores_loop():
    """Outage must disengage the loop; end must re-engage and restore harvest."""
    a = PlantAdapter()
    assert a.plant.loop_engaged is True
    r = outage(a)
    assert r["loop_engaged"] == 0.0 and a.plant.loop_engaged is False
    # During the outage, H becomes an exogenous supply process.
    for _ in range(20):
        a.write_actuators(Action())
    assert a.read_state()["H"] > 0.2
    r2 = outage_end(a)
    assert r2["loop_engaged"] == 1.0 and a.plant.loop_engaged is True
    # Re-engagement restores the metered harvest level (no inherited subsidy).
    assert abs(a.read_state()["H"] - a.plant.p.harvest_rate) < 1e-9
