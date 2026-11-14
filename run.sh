#!/usr/bin/env bash
# Soil image -> AI analysis -> companies whose products fit that soil.
# Usage: ./run.sh [image]        (default: images/soil.jpg)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
IMAGE="$(realpath "${1:-$ROOT/images/soil.jpg}")"
REPORT="$ROOT/trading/soil_report.txt"

PYTHON="$ROOT/ai/venv/bin/python"
[ -x "$PYTHON" ] || PYTHON=python3

# 1. Python: analyze the image and write the soil report.
rm -f "$REPORT"
(cd "$ROOT/ai" && "$PYTHON" soil_analyzer.py "$IMAGE" --out "$REPORT")

# 2. C++: rebuild the trader if the source changed, then match companies.
cd "$ROOT/trading"
if [ ! -x trader ] || [ trader.cpp -nt trader ]; then
    g++ -std=c++11 trader.cpp -o trader -lcurl -pthread
fi
echo
echo "============================================================"
./trader --soil "$REPORT"
