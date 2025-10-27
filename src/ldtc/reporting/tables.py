"""Reporting: Table writers.

CSV writers for verification tables with enforcement of the no-raw-LREG policy.

See Also:
    paper/main.tex — Reporting & Figures; Export policy.
"""

from __future__ import annotations

import csv
from typing import List, Dict, Any


_BANNED_RAW_KEYS = {"L_loop", "L_ex", "ci_loop", "ci_ex"}


def _assert_no_raw_keys(rows: List[Dict[str, Any]]) -> None:
    """Defensive check that rows do not contain raw LREG fields.

    Raises:
        ValueError: If any forbidden key is present.
    """
    for r in rows:
        if any(k in r for k in _BANNED_RAW_KEYS):
            raise ValueError(
                "raw LREG fields detected in reporting rows; export blocked"
            )


def write_sc1_table(rows: List[Dict[str, Any]], out_csv: str) -> None:
    """Write SC1 result rows to a CSV file.

    Args:
        rows: List of dicts with consistent keys across rows.
        out_csv: Target CSV path to write.
    """
    if not rows:
        return
    _assert_no_raw_keys(rows)
    cols = list(rows[0].keys())
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)
