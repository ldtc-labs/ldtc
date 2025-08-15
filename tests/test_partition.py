from __future__ import annotations

from ldtc.lmeas.partition import PartitionManager


def test_partition():
    pm = PartitionManager(N_signals=5, seed_C=[0, 1])
    p = pm.get()
    assert set(p.C) == {0, 1}
    assert set(p.Ex) == {2, 3, 4}
    # propose a change but with insufficient ΔM (should not flip)
    pm.maybe_regrow(
        [0, 1, 2], delta_M_db=0.1, delta_M_min_db=0.5, consecutive_required=2
    )
    p2 = pm.get()
    assert set(p2.C) == {0, 1}
    # now provide sufficient ΔM but only once; still no flip until streak met
    pm.maybe_regrow(
        [0, 1, 2], delta_M_db=0.6, delta_M_min_db=0.5, consecutive_required=2
    )
    p3 = pm.get()
    assert set(p3.C) == {0, 1}
    # second consecutive confirmation -> accept
    pm.maybe_regrow(
        [0, 1, 2], delta_M_db=0.7, delta_M_min_db=0.5, consecutive_required=2
    )
    p4 = pm.get()
    assert set(p4.C) == {0, 1, 2}
    # freeze prevents further flips
    pm.freeze(True)
    pm.maybe_regrow(
        [0, 1, 2, 3], delta_M_db=1.0, delta_M_min_db=0.5, consecutive_required=1
    )
    p5 = pm.get()
    assert set(p5.C) == {0, 1, 2}
