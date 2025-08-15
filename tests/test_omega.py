from __future__ import annotations

from ldtc.plant.adapter import PlantAdapter
from ldtc.omega.power_sag import apply as sag
from ldtc.omega.ingress_flood import apply as flood
from ldtc.omega.command_conflict import apply as conflict


def test_omega_calls():
    a = PlantAdapter()
    r1 = sag(a, drop=0.2)
    assert "H_new" in r1
    r2 = flood(a, mult=2.0)
    assert "demand" in r2
    r3 = conflict(a)
    assert r3["cmd"] == "hard_shutdown"
