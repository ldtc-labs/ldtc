#!/usr/bin/env bash
set -euo pipefail
# Power-sag example (you can extend with more Ω)
python -m ldtc.cli.main omega-power-sag --config configs/profile_r0.yml --drop "${1:-0.35}" --duration "${2:-8}"
