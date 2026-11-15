#!/usr/bin/env bash
# Soil image -> AI analysis -> companies whose products fit that soil.
# Runs inside the Docker container; the project folder is mounted at /app.
#
#   docker compose run --rm soil                                    # uses images/soil/soil.jpg
#   docker compose run --rm soil images/soil/mysoil.jpg             # your own image (path inside the project)
#   docker compose run --rm soil prices                             # live prices for every company
#   docker compose run --rm stock history                           # download monthly price history for every company
#   docker compose run --rm stockFutures backtest                   # soil match, then backtest those companies
#   docker compose run --rm stockFutures backtest images/soil/mysoil.jpg
#   docker compose run --rm futures backtest                        # palm oil backtest only (data/main.py), no soil analysis
#   docker compose run --rm stocks backtest                         # stocks-only chart, no soil analysis or palm oil signal
#
# soil, stock, stockFutures, futures and stocks are five names for this same container (see compose.yaml).
# compose.yaml sets APP_SERVICE to the name that was used, because "backtest" means something different for each.
#
# Charts are saved to images/results/.
set -euo pipefail

ROOT=/app
SERVICE="${APP_SERVICE:-soil}"
REPORT="$ROOT/trading/soil_report.txt"

if [ "${1:-}" = "prices" ]; then
    cd "$ROOT/trading"
    exec trader
fi

if [ "${1:-}" = "history" ]; then
    cd "$ROOT/data"
    exec python fetch_history.py
fi

# Palm oil backtest only: "futures backtest" (the older "model" still works).
if [ "${1:-}" = "model" ] || { [ "${1:-}" = "backtest" ] && [ "$SERVICE" = "futures" ]; }; then
    # main.py looks for data/climatestatistics.csv from the project root.
    cd "$ROOT"
    exec python data/main.py
fi

# Stocks-only chart: "stocks backtest".
if [ "${1:-}" = "backtest" ] && [ "$SERVICE" = "stocks" ]; then
    if [ ! -d "$ROOT/data/stock_history" ]; then
        echo "ERROR: no price history yet. Run this first: docker compose run --rm stock history" >&2
        exit 1
    fi
    cd "$ROOT/data"
    exec python stocks_growth.py
fi

# Everything below is the soil pipeline; "stockFutures backtest" adds the stock backtest at the end.

BACKTEST=no
if [ "${1:-}" = "backtest" ]; then
    BACKTEST=yes
    shift
    if [ ! -d "$ROOT/data/stock_history" ]; then
        echo "ERROR: no price history yet. Run this first: docker compose run --rm stock history" >&2
        exit 1
    fi
fi

if [ ! -f "$ROOT/ai/.env" ]; then
    echo "ERROR: ai/.env not found. Copy ai/.env.example to ai/.env and add your Gemini key." >&2
    exit 1
fi

# Accept Windows-style paths (images\soil\soil.jpg) as well.
IMAGE="${1:-images/soil/soil.jpg}"
IMAGE="${IMAGE//\\//}"
cd "$ROOT"
if [ ! -f "$IMAGE" ]; then
    echo "ERROR: image not found: $IMAGE" >&2
    echo "Put the image inside the project folder (for example in images/soil/) and pass that path." >&2
    exit 1
fi
IMAGE="$(realpath "$IMAGE")"

# 1. Python: analyze the image and write the soil report.
rm -f "$REPORT"
(cd "$ROOT/ai" && python soil_analyzer.py "$IMAGE" --out "$REPORT")

# 2. C++: match companies to the soil report (also saves them to trading/soil_matches.csv).
cd "$ROOT/trading"
echo
echo "============================================================"
trader --soil "$REPORT"

# 3. Python: backtest the matched companies against the palm oil rain signal.
if [ "$BACKTEST" = "yes" ]; then
    cd "$ROOT/data"
    echo
    python stock_backtest.py
fi
