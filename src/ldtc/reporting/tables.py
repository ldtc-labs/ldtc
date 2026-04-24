"""CSV writers for SC1 result tables.

The writers in this module enforce LDTC's "no raw LREG" export policy
(see [`guardrails.lreg`][ldtc.guardrails.lreg]): if a row dict ever
contains `L_loop`, `L_ex`, `ci_loop`, or `ci_ex`, the writer refuses
to emit the file. This is a second line of defense after the same
check inside [`attest.exporter`][ldtc.attest.exporter]; together they
guarantee that raw `𝓛` values can leave neither the device-signed
indicator artifact nor the human-facing CSV table.

See Also:
    `paper/main.tex`: Reporting & Figures; Export policy.
"""

from __future__ import annotations

import csv
from typing import Any, Dict, List

_BANNED_RAW_KEYS = {"L_loop", "L_ex", "ci_loop", "ci_ex"}


def _assert_no_raw_keys(rows: List[Dict[str, Any]]) -> None:
    """Reject rows that contain raw LREG fields.

    Args:
        rows: Candidate rows to check.

    Raises:
        ValueError: If any row contains `L_loop`, `L_ex`, `ci_loop`, or
            `ci_ex`. The export is blocked before any file is written.
    """
    for r in rows:
        if any(k in r for k in _BANNED_RAW_KEYS):
            raise ValueError("raw LREG fields detected in reporting rows; export blocked")


def write_sc1_table(rows: List[Dict[str, Any]], out_csv: str) -> None:
    """Write SC1 result rows to a CSV file.

    Column order is taken from the first row's keys, so callers should
    use a stable dict layout (e.g., always emit the same fields in the
    same order) to keep diffs across runs minimal.

    Args:
        rows: List of dicts with consistent keys across rows. Must not
            contain any raw LREG field (`L_loop`, `L_ex`, `ci_loop`,
            `ci_ex`); the writer refuses such rows.
        out_csv: Target CSV path. The file is created or overwritten.

    Raises:
        ValueError: If any row contains a banned raw LREG field.
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
