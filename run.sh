#!/usr/bin/env bash
# Soil image -> AI analysis -> companies whose products fit that soil.
# Runs inside the Docker container; the project folder is mounted at /app.
#
#   docker compose run --rm soil                     # uses images/soil.jpg
#   docker compose run --rm soil images/mysoil.jpg   # your own image (path inside the project)
#   docker compose run --rm soil prices              # live prices for every company
set -euo pipefail

ROOT=/app
REPORT="$ROOT/trading/soil_report.txt"

if [ "${1:-}" = "prices" ]; then
    cd "$ROOT/trading"
    exec trader
fi

if [ ! -f "$ROOT/ai/.env" ]; then
    echo "ERROR: ai/.env not found. Copy ai/.env.example to ai/.env and add your Gemini key." >&2
    exit 1
fi

# Accept Windows-style paths (images\soil.jpg) as well.
IMAGE="${1:-images/soil.jpg}"
IMAGE="${IMAGE//\\//}"
cd "$ROOT"
if [ ! -f "$IMAGE" ]; then
    echo "ERROR: image not found: $IMAGE" >&2
    echo "Put the image inside the project folder (for example in images/) and pass that path." >&2
    exit 1
fi
IMAGE="$(realpath "$IMAGE")"

# 1. Python: analyze the image and write the soil report.
rm -f "$REPORT"
(cd "$ROOT/ai" && python soil_analyzer.py "$IMAGE" --out "$REPORT")

# 2. C++: match companies to the soil report.
cd "$ROOT/trading"
echo
echo "============================================================"
trader --soil "$REPORT"
