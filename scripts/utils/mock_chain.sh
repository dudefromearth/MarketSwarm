#!/opt/homebrew/bin/bash
set -euo pipefail

###############################################
# MarketSwarm – mock_massive foreground startup
###############################################

# Resolve root correctly (script in scripts/utils/)
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SERVICE="mock_massive"
MAIN="$ROOT/services/mock_massive/main.py"

VENV="$ROOT/.venv"
VENV_PY="$VENV/bin/python"

# Check python exists
if [[ ! -x "$VENV_PY" ]]; then
  echo "Error: Python not found at $VENV_PY"
  echo "Activate venv or run: python -m venv $ROOT/.venv"
  exit 1
fi

# Required env
export MOCK_CAPTURE_DIR="/Users/ernie/MarketSwarm/ws_captures"
export MOCK_MODE="${MOCK_MODE:-development}"

echo "──────────────────────────────────────────────"
echo " MarketSwarm – mock_massive foreground startup"
echo "──────────────────────────────────────────────"
echo "Root        : $ROOT"
echo "Mode        : $MOCK_MODE"
echo "Capture Dir : $MOCK_CAPTURE_DIR"
echo "Python      : $VENV_PY"
echo "Main        : $MAIN"
echo "──────────────────────────────────────────────"
echo "Starting service — logs below"
echo "Press Ctrl-C to stop"
echo "──────────────────────────────────────────────"

cd "$ROOT"
export SERVICE_ID="$SERVICE"

exec "$VENV_PY" "$MAIN"