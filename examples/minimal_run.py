from __future__ import annotations

import os
import subprocess
import sys


# Minimal: run baseline with default profile
def main():
    cfg = os.path.join("configs", "profile_r0.yml")
    subprocess.run([sys.executable, "-m", "ldtc.cli.main", "run", "--config", cfg], check=True)


if __name__ == "__main__":
    main()
