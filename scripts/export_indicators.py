#!/usr/bin/env python3
"""Scripts: Pretty-print exported indicator JSONL files.

Reads indicator JSONL files from ``artifacts/indicators`` and prints them
to stdout with indentation for quick inspection.
"""
from __future__ import annotations

import glob
import json
import os


def main() -> None:
    """Print indicators in artifacts/indicators as pretty JSON.

    Scans for ``*.jsonl`` files and prints each line as indented JSON.
    """
    paths = sorted(glob.glob(os.path.join("artifacts", "indicators", "*.jsonl")))
    if not paths:
        print("No indicators found.")
        return
    for p in paths:
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                print(json.dumps(json.loads(line), indent=2))


if __name__ == "__main__":
    main()
