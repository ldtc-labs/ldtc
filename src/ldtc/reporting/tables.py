from __future__ import annotations

import csv
from typing import List, Dict, Any


_BANNED_RAW_KEYS = {"L_loop", "L_ex", "ci_loop", "ci_ex"}


def _assert_no_raw_keys(rows: List[Dict[str, Any]]) -> None:
    for r in rows:
        if any(k in r for k in _BANNED_RAW_KEYS):
            raise ValueError(
                "raw LREG fields detected in reporting rows; export blocked"
            )


def write_sc1_table(rows: List[Dict[str, Any]], out_csv: str) -> None:
    if not rows:
        return
    _assert_no_raw_keys(rows)
    cols = list(rows[0].keys())
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)
