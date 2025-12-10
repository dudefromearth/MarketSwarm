#!/opt/homebrew/bin/bash
set -euo pipefail

###############################################
# MarketSwarm – massive (Massive Market Model)
# Foreground dev runner (no PID, no log file)
#
# Always:
#   - MASSIVE_WS_ENABLED=true
#   - WS expiry = today (UTC, YYYYMMDD)
#   - All params hard-coded here; edit in this file.
###############################################

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE="massive"
MAIN="$ROOT/services/massive/main.py"

VENV="$ROOT/.venv"
VENV_PY="$VENV/bin/python"

###############################################
# Core Redis endpoints
###############################################
export SYSTEM_REDIS_URL="redis://127.0.0.1:6379"
export MARKET_REDIS_URL="redis://127.0.0.1:6380"
export INTEL_REDIS_URL="redis://127.0.0.1:6381"

###############################################
# Debug
###############################################
export DEBUG_MASSIVE="false"      # flip to "false" if you want less noise

###############################################
# Symbol / underlying selection
# (edit these if you want a different underlyer)
###############################################
export MASSIVE_SYMBOL="I:SPX"    # I:SPX, I:NDX, SPY, QQQ
export MASSIVE_UNDERLYING="SPX"  # SPX, NDX, SPY, QQQ

# Strike step for WS channels (SPX=5, NDX=10, SPY/QQQ=1, etc.)
export MASSIVE_WS_STRIKE_STEP=5

# Massive API key
export MASSIVE_API_KEY="pdjraOWSpDbg3ER_RslZYe3dmn4Y7WCC"  # change to your real key

###############################################
# Spot cadence (frequency + trail)
###############################################
export MASSIVE_SPOT_INTERVAL_SEC=1
export MASSIVE_SPOT_TRAIL_WINDOW_SEC=86400     # 24h
export MASSIVE_SPOT_TRAIL_TTL_SEC=172800       # 48h

###############################################
# Chain cadence (frequency + range + TTL)
###############################################
export MASSIVE_CHAIN_INTERVAL_SEC=60           # refresh full chain every 60s
export MASSIVE_CHAIN_STRIKE_RANGE=150          # ± points around ATM
export MASSIVE_CHAIN_NUM_EXPIRATIONS=5         # how many expiries to snapshot
export MASSIVE_CHAIN_SNAPSHOT_TTL_SEC=600      # chain snapshot TTL
export MASSIVE_CHAIN_TRAIL_WINDOW_SEC=86400
export MASSIVE_CHAIN_TRAIL_TTL_SEC=172800

###############################################
# WebSocket config – always ON
###############################################
export MASSIVE_WS_ENABLED="true"
export MASSIVE_WS_URL="wss://socket.massive.com/options"
export MASSIVE_WS_RECONNECT_DELAY_SEC=5.0

# Dynamically choose today (UTC) as WS expiry: YYYYMMDD
export MASSIVE_WS_EXPIRY_YYYYMMDD="$(date -u +%Y%m%d)"

# Legacy / unused but harmless
export MASSIVE_WS_PARAMS=""

###############################################
# Orchestrator hints (used by some runners)
###############################################
export MASSIVE_LOOP_SLEEP=1.0
export MASSIVE_SNAPSHOT_INTERVAL=10

###############################################
# Run massive in foreground
###############################################
run_foreground() {
  clear
  echo "──────────────────────────────────────────────"
  echo " MarketSwarm – massive (foreground runner)"
  echo "──────────────────────────────────────────────"
  echo "ROOT:                           $ROOT"
  echo "SERVICE_ID:                     $SERVICE"
  echo "VENV_PY:                        $VENV_PY"
  echo "MAIN:                           $MAIN"
  echo
  echo "DEBUG_MASSIVE:                  $DEBUG_MASSIVE"
  echo "MASSIVE_SYMBOL:                 $MASSIVE_SYMBOL"
  echo "MASSIVE_UNDERLYING:             $MASSIVE_UNDERLYING"
  echo
  echo "MASSIVE_SPOT_INTERVAL_SEC:      $MASSIVE_SPOT_INTERVAL_SEC"
  echo "MASSIVE_SPOT_TRAIL_WINDOW_SEC:  $MASSIVE_SPOT_TRAIL_WINDOW_SEC"
  echo "MASSIVE_SPOT_TRAIL_TTL_SEC:     $MASSIVE_SPOT_TRAIL_TTL_SEC"
  echo
  echo "MASSIVE_CHAIN_INTERVAL_SEC:     $MASSIVE_CHAIN_INTERVAL_SEC"
  echo "MASSIVE_CHAIN_STRIKE_RANGE:     $MASSIVE_CHAIN_STRIKE_RANGE"
  echo "MASSIVE_CHAIN_NUM_EXPIRATIONS:  $MASSIVE_CHAIN_NUM_EXPIRATIONS"
  echo "MASSIVE_CHAIN_SNAPSHOT_TTL_SEC: $MASSIVE_CHAIN_SNAPSHOT_TTL_SEC"
  echo "MASSIVE_CHAIN_TRAIL_WINDOW_SEC: $MASSIVE_CHAIN_TRAIL_WINDOW_SEC"
  echo "MASSIVE_CHAIN_TRAIL_TTL_SEC:    $MASSIVE_CHAIN_TRAIL_TTL_SEC"
  echo
  echo "MASSIVE_WS_ENABLED:             $MASSIVE_WS_ENABLED"
  echo "MASSIVE_WS_URL:                 $MASSIVE_WS_URL"
  echo "MASSIVE_WS_STRIKE_STEP:         $MASSIVE_WS_STRIKE_STEP"
  echo "MASSIVE_WS_EXPIRY_YYYYMMDD:     $MASSIVE_WS_EXPIRY_YYYYMMDD"
  echo "MASSIVE_WS_RECONNECT_DELAY_SEC: $MASSIVE_WS_RECONNECT_DELAY_SEC"
  echo
  echo "MASSIVE_LOOP_SLEEP:             $MASSIVE_LOOP_SLEEP s"
  echo "MASSIVE_SNAPSHOT_INTERVAL:      $MASSIVE_SNAPSHOT_INTERVAL s"
  echo "──────────────────────────────────────────────"
  echo
  echo "Running massive in foreground. Ctrl+C to stop."
  echo

  cd "$ROOT"
  export SERVICE_ID="$SERVICE"

  exec "$VENV_PY" "$MAIN"
}

###############################################
# Optional trivial help
###############################################
if [[ "${1:-}" == "help" || "${1:-}" == "-h" ]]; then
  echo "Usage: $(basename "$0")"
  echo
  echo "Runs the Massive service in foreground with:"
  echo "  - WS enabled"
  echo "  - WS expiry = today (UTC)"
  echo "  - All params hard-coded inside this script."
  echo
  echo "Edit ms-massive.sh to change symbols, cadences, etc."
  exit 0
fi

run_foreground