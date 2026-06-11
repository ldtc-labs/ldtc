"""Summarize an LDTC run's audit log: validity, NC1 fraction, M stats, SC1.

Usage: python scripts/_summarize_run.py <run_dir_or_audit.jsonl>
If a directory is given, the newest matching audit.jsonl under it is used.
"""

from __future__ import annotations

import json
import os
import sys
from statistics import median


def _resolve(path: str) -> str:
    if os.path.isfile(path):
        return path
    cand = os.path.join(path, "audits", "audit.jsonl")
    if os.path.isfile(cand):
        return cand
    raise SystemExit(f"no audit.jsonl found at {path}")


def main() -> None:
    path = _resolve(sys.argv[1])
    nc1: list[bool] = []
    m: list[float] = []
    invalid: list[str] = []
    refusal: list[dict] = []
    sc1: dict | None = None
    red_flags: list[dict] = []
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        e = json.loads(line)
        ev = e.get("event")
        det = e.get("details", {}) or {}
        if ev == "window_measured":
            nc1.append(bool(det.get("nc1")))
            if det.get("M") is not None:
                m.append(float(det["M"]))
        elif ev == "run_invalidated":
            invalid.append(det.get("reason", "?"))
        elif ev in ("command_refusal_result", "refusal_event"):
            refusal.append(det)
        elif ev == "sc1_result":
            sc1 = det
        elif "red_flag" in str(ev):
            red_flags.append(det)

    print(f"audit: {path}")
    print(f"valid: {not invalid}  invalidations: {invalid}")
    if nc1:
        frac = sum(nc1) / len(nc1)
        print(f"NC1: {sum(nc1)}/{len(nc1)} windows true ({frac:.1%})")
    if m:
        print(f"M dB: median={median(m):.2f} min={min(m):.2f} max={max(m):.2f}")
    if sc1 is not None:
        print(f"SC1: {sc1}")
    if refusal:
        print(f"refusal: {refusal}")
    if red_flags:
        print(f"red_flags: {red_flags}")


if __name__ == "__main__":
    main()
