#!/usr/bin/env python3
from __future__ import annotations

import glob
import json
import os


def main() -> None:
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
