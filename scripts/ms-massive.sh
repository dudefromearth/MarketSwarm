#!/opt/homebrew/bin/bash
set -euo pipefail

###############################################
# MarketSwarm – massive (Massive Market Model)
# Foreground dev runner (no PID, no log file)
###############################################

# ------------------------------------------------
# Environment
# ------------------------------------------------
export SYSTEM_REDIS_URL="redis://127.0.0.1:6379"
export MARKET_REDIS_URL="redis://127.0.0.1:6380"
export INTEL_REDIS_URL="redis://127.0.0.1:6381"

export DEBUG_MASSIVE="${DEBUG_MASSIVE:-false}"

###############################################
# Symbol selection (one symbol per service)
###############################################
export MASSIVE_SYMBOL="${MASSIVE_SYMBOL:-I:SPX}"
ALLOWED_SYMBOLS="I:SPX I:NDX SPY QQQ"
export MASSIVE_API_KEY="${MASSIVE_API_KEY:-pdjraOWSpDbg3ER_RslZYe3dmn4Y7WCC}"

###############################################
# Spot cadence (frequency + trail)
###############################################
export MASSIVE_SPOT_INTERVAL_SEC="${MASSIVE_SPOT_INTERVAL_SEC:-1}"
export MASSIVE_SPOT_TRAIL_WINDOW_SEC="${MASSIVE_SPOT_TRAIL_WINDOW_SEC:-86400}"   # 24h
export MASSIVE_SPOT_TRAIL_TTL_SEC="${MASSIVE_SPOT_TRAIL_TTL_SEC:-172800}"       # 48h

###############################################
# Chain cadence (frequency + range + TTL)
###############################################
# How often to refresh options chain (seconds)
export MASSIVE_CHAIN_INTERVAL_SEC="${MASSIVE_CHAIN_INTERVAL_SEC:-60}"

# ±points around ATM/spot to keep in the chain snapshot
export MASSIVE_CHAIN_STRIKE_RANGE="${MASSIVE_CHAIN_STRIKE_RANGE:-150}"

# How many expirations to load per cycle
export MASSIVE_CHAIN_NUM_EXPIRATIONS="${MASSIVE_CHAIN_NUM_EXPIRATIONS:-5}"

# TTL for CHAIN:...:snap:* keys
export MASSIVE_CHAIN_SNAPSHOT_TTL_SEC="${MASSIVE_CHAIN_SNAPSHOT_TTL_SEC:-600}"

# Window for CHAIN:...:trail score trimming (seconds)
export MASSIVE_CHAIN_TRAIL_WINDOW_SEC="${MASSIVE_CHAIN_TRAIL_WINDOW_SEC:-86400}"

# TTL for CHAIN:...:trail keys
export MASSIVE_CHAIN_TRAIL_TTL_SEC="${MASSIVE_CHAIN_TRAIL_TTL_SEC:-172800}"

# General orchestrator loop hints (if needed later)
export MASSIVE_LOOP_SLEEP="${MASSIVE_LOOP_SLEEP:-1.0}"
export MASSIVE_SNAPSHOT_INTERVAL="${MASSIVE_SNAPSHOT_INTERVAL:-10}"

BREW_PY="/opt/homebrew/bin/python3.14"
BREW_REDIS="/opt/homebrew/bin/redis-cli"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE="massive"
MAIN="$ROOT/services/massive/main.py"

VENV="$ROOT/.venv"
VENV_PY="$VENV/bin/python"

###############################################
# UI Helpers
###############################################
line() { echo "──────────────────────────────────────────────"; }

check_tools() {
  for cmd in "$BREW_PY" "$VENV_PY" "$BREW_REDIS"; do
    if [[ -x "$cmd" ]]; then
      echo "Found $cmd"
    else
      echo "WARNING: Missing $cmd"
    fi
  done
}

run_foreground() {
  clear
  line
  echo " Launching $SERVICE (foreground)"
  line
  echo "ROOT:                           $ROOT"
  echo "SERVICE_ID:                     $SERVICE"
  echo "VENV_PY:                        $VENV_PY"
  echo "MAIN:                           $MAIN"
  echo "DEBUG_MASSIVE:                  $DEBUG_MASSIVE"
  echo "MASSIVE_SYMBOL:                 $MASSIVE_SYMBOL"
  echo "MASSIVE_SPOT_INTERVAL_SEC:      $MASSIVE_SPOT_INTERVAL_SEC"
  echo "MASSIVE_SPOT_TRAIL_WINDOW_SEC:  $MASSIVE_SPOT_TRAIL_WINDOW_SEC"
  echo "MASSIVE_SPOT_TRAIL_TTL_SEC:     $MASSIVE_SPOT_TRAIL_TTL_SEC"
  echo "MASSIVE_CHAIN_INTERVAL_SEC:     $MASSIVE_CHAIN_INTERVAL_SEC"
  echo "MASSIVE_CHAIN_STRIKE_RANGE:     $MASSIVE_CHAIN_STRIKE_RANGE"
  echo "MASSIVE_CHAIN_NUM_EXPIRATIONS:  $MASSIVE_CHAIN_NUM_EXPIRATIONS"
  echo "MASSIVE_CHAIN_SNAPSHOT_TTL_SEC: $MASSIVE_CHAIN_SNAPSHOT_TTL_SEC"
  echo "MASSIVE_CHAIN_TRAIL_WINDOW_SEC: $MASSIVE_CHAIN_TRAIL_WINDOW_SEC"
  echo "MASSIVE_CHAIN_TRAIL_TTL_SEC:    $MASSIVE_CHAIN_TRAIL_TTL_SEC"
  echo "MASSIVE_LOOP_SLEEP:             $MASSIVE_LOOP_SLEEP s"
  echo "MASSIVE_SNAPSHOT_INTERVAL:      $MASSIVE_SNAPSHOT_INTERVAL s"
  line
  echo ""

  if [[ " $ALLOWED_SYMBOLS " != *" $MASSIVE_SYMBOL "* ]]; then
    echo "WARNING: MASSIVE_SYMBOL='$MASSIVE_SYMBOL' not in allowed set: $ALLOWED_SYMBOLS"
    echo ""
  fi

  check_tools
  echo ""
  echo "Running $SERVICE in foreground. Ctrl+C to stop."
  echo ""

  cd "$ROOT"
  export SERVICE_ID="$SERVICE"
  export DEBUG_MASSIVE
  export MASSIVE_SYMBOL
  export MASSIVE_API_KEY

  export MASSIVE_SPOT_INTERVAL_SEC
  export MASSIVE_SPOT_TRAIL_WINDOW_SEC
  export MASSIVE_SPOT_TRAIL_TTL_SEC

  export MASSIVE_CHAIN_INTERVAL_SEC
  export MASSIVE_CHAIN_STRIKE_RANGE
  export MASSIVE_CHAIN_NUM_EXPIRATIONS
  export MASSIVE_CHAIN_SNAPSHOT_TTL_SEC
  export MASSIVE_CHAIN_TRAIL_WINDOW_SEC
  export MASSIVE_CHAIN_TRAIL_TTL_SEC

  export MASSIVE_LOOP_SLEEP
  export MASSIVE_SNAPSHOT_INTERVAL

  exec "$VENV_PY" "$MAIN"
}

###############################################
# Menu
###############################################
menu() {
  while true; do
    clear
    line
    echo " MarketSwarm – massive (Massive Market Model)"
    line
    echo ""
    echo "Current configuration:"
    echo "  DEBUG_MASSIVE                  = $DEBUG_MASSIVE"
    echo "  MASSIVE_SYMBOL                 = $MASSIVE_SYMBOL"
    echo "  MASSIVE_SPOT_INTERVAL_SEC      = $MASSIVE_SPOT_INTERVAL_SEC"
    echo "  MASSIVE_SPOT_TRAIL_WINDOW_SEC  = $MASSIVE_SPOT_TRAIL_WINDOW_SEC"
    echo "  MASSIVE_SPOT_TRAIL_TTL_SEC     = $MASSIVE_SPOT_TRAIL_TTL_SEC"
    echo "  MASSIVE_CHAIN_INTERVAL_SEC     = $MASSIVE_CHAIN_INTERVAL_SEC"
    echo "  MASSIVE_CHAIN_STRIKE_RANGE     = $MASSIVE_CHAIN_STRIKE_RANGE"
    echo "  MASSIVE_CHAIN_NUM_EXPIRATIONS  = $MASSIVE_CHAIN_NUM_EXPIRATIONS"
    echo "  MASSIVE_CHAIN_SNAPSHOT_TTL_SEC = $MASSIVE_CHAIN_SNAPSHOT_TTL_SEC"
    echo "  MASSIVE_CHAIN_TRAIL_WINDOW_SEC = $MASSIVE_CHAIN_TRAIL_WINDOW_SEC"
    echo "  MASSIVE_CHAIN_TRAIL_TTL_SEC    = $MASSIVE_CHAIN_TRAIL_TTL_SEC"
    echo ""
    echo "Select Option:"
    echo ""
    echo "  1) Run massive (foreground)"
    echo "  2) Toggle DEBUG_MASSIVE"
    echo "  3) Change MASSIVE_SYMBOL"
    echo "  4) Change MASSIVE_SPOT_INTERVAL_SEC"
    echo "  5) Change MASSIVE_SPOT_TRAIL_WINDOW_SEC"
    echo "  6) Change MASSIVE_SPOT_TRAIL_TTL_SEC"
    echo "  7) Change MASSIVE_CHAIN_INTERVAL_SEC"
    echo "  8) Change MASSIVE_CHAIN_STRIKE_RANGE"
    echo "  9) Change MASSIVE_CHAIN_NUM_EXPIRATIONS"
    echo " 10) Change MASSIVE_CHAIN_SNAPSHOT_TTL_SEC"
    echo " 11) Change MASSIVE_CHAIN_TRAIL_WINDOW_SEC"
    echo " 12) Change MASSIVE_CHAIN_TRAIL_TTL_SEC"
    echo " 13) Quit"
    echo ""
    line
    read -rp "Enter choice [1-13]: " CH
    echo ""

    case "$CH" in
      1) run_foreground ;;  # exec, doesn't return
      2)
        if [[ "$DEBUG_MASSIVE" == "true" ]]; then
          DEBUG_MASSIVE="false"
        else
          DEBUG_MASSIVE="true"
        fi
        export DEBUG_MASSIVE
        echo "DEBUG_MASSIVE is now: $DEBUG_MASSIVE"
        sleep 1
        ;;
      3)
        read -rp "Enter MASSIVE_SYMBOL (current: $MASSIVE_SYMBOL): " NEW_SYM
        if [[ -n "$NEW_SYM" ]]; then
          MASSIVE_SYMBOL="$NEW_SYM"
          export MASSIVE_SYMBOL
          echo "MASSIVE_SYMBOL is now: $MASSIVE_SYMBOL"
        else
          echo "MASSIVE_SYMBOL unchanged."
        fi
        sleep 1
        ;;
      4)
        read -rp "Enter MASSIVE_SPOT_INTERVAL_SEC (current: $MASSIVE_SPOT_INTERVAL_SEC): " NEW_INT
        if [[ -n "$NEW_INT" ]]; then
          MASSIVE_SPOT_INTERVAL_SEC="$NEW_INT"
          export MASSIVE_SPOT_INTERVAL_SEC
          echo "MASSIVE_SPOT_INTERVAL_SEC is now: $MASSIVE_SPOT_INTERVAL_SEC"
        else
          echo "MASSIVE_SPOT_INTERVAL_SEC unchanged."
        fi
        sleep 1
        ;;
      5)
        read -rp "Enter MASSIVE_SPOT_TRAIL_WINDOW_SEC (current: $MASSIVE_SPOT_TRAIL_WINDOW_SEC): " NEW_WIN
        if [[ -n "$NEW_WIN" ]]; then
          MASSIVE_SPOT_TRAIL_WINDOW_SEC="$NEW_WIN"
          export MASSIVE_SPOT_TRAIL_WINDOW_SEC
          echo "MASSIVE_SPOT_TRAIL_WINDOW_SEC is now: $MASSIVE_SPOT_TRAIL_WINDOW_SEC"
        else
          echo "MASSIVE_SPOT_TRAIL_WINDOW_SEC unchanged."
        fi
        sleep 1
        ;;
      6)
        read -rp "Enter MASSIVE_SPOT_TRAIL_TTL_SEC (current: $MASSIVE_SPOT_TRAIL_TTL_SEC): " NEW_TTL
        if [[ -n "$NEW_TTL" ]]; then
          MASSIVE_SPOT_TRAIL_TTL_SEC="$NEW_TTL"
          export MASSIVE_SPOT_TRAIL_TTL_SEC
          echo "MASSIVE_SPOT_TRAIL_TTL_SEC is now: $MASSIVE_SPOT_TRAIL_TTL_SEC"
        else
          echo "MASSIVE_SPOT_TRAIL_TTL_SEC unchanged."
        fi
        sleep 1
        ;;
      7)
        read -rp "Enter MASSIVE_CHAIN_INTERVAL_SEC (current: $MASSIVE_CHAIN_INTERVAL_SEC): " NEW_INT
        if [[ -n "$NEW_INT" ]]; then
          MASSIVE_CHAIN_INTERVAL_SEC="$NEW_INT"
          export MASSIVE_CHAIN_INTERVAL_SEC
          echo "MASSIVE_CHAIN_INTERVAL_SEC is now: $MASSIVE_CHAIN_INTERVAL_SEC"
        else
          echo "MASSIVE_CHAIN_INTERVAL_SEC unchanged."
        fi
        sleep 1
        ;;
      8)
        read -rp "Enter MASSIVE_CHAIN_STRIKE_RANGE (current: $MASSIVE_CHAIN_STRIKE_RANGE): " NEW_RANGE
        if [[ -n "$NEW_RANGE" ]]; then
          MASSIVE_CHAIN_STRIKE_RANGE="$NEW_RANGE"
          export MASSIVE_CHAIN_STRIKE_RANGE
          echo "MASSIVE_CHAIN_STRIKE_RANGE is now: $MASSIVE_CHAIN_STRIKE_RANGE"
        else
          echo "MASSIVE_CHAIN_STRIKE_RANGE unchanged."
        fi
        sleep 1
        ;;
      9)
        read -rp "Enter MASSIVE_CHAIN_NUM_EXPIRATIONS (current: $MASSIVE_CHAIN_NUM_EXPIRATIONS): " NEW_NUM
        if [[ -n "$NEW_NUM" ]]; then
          MASSIVE_CHAIN_NUM_EXPIRATIONS="$NEW_NUM"
          export MASSIVE_CHAIN_NUM_EXPIRATIONS
          echo "MASSIVE_CHAIN_NUM_EXPIRATIONS is now: $MASSIVE_CHAIN_NUM_EXPIRATIONS"
        else
          echo "MASSIVE_CHAIN_NUM_EXPIRATIONS unchanged."
        fi
        sleep 1
        ;;
      10)
        read -rp "Enter MASSIVE_CHAIN_SNAPSHOT_TTL_SEC (current: $MASSIVE_CHAIN_SNAPSHOT_TTL_SEC): " NEW_TTL
        if [[ -n "$NEW_TTL" ]]; then
          MASSIVE_CHAIN_SNAPSHOT_TTL_SEC="$NEW_TTL"
          export MASSIVE_CHAIN_SNAPSHOT_TTL_SEC
          echo "MASSIVE_CHAIN_SNAPSHOT_TTL_SEC is now: $MASSIVE_CHAIN_SNAPSHOT_TTL_SEC"
        else
          echo "MASSIVE_CHAIN_SNAPSHOT_TTL_SEC unchanged."
        fi
        sleep 1
        ;;
      11)
        read -rp "Enter MASSIVE_CHAIN_TRAIL_WINDOW_SEC (current: $MASSIVE_CHAIN_TRAIL_WINDOW_SEC): " NEW_WIN
        if [[ -n "$NEW_WIN" ]]; then
          MASSIVE_CHAIN_TRAIL_WINDOW_SEC="$NEW_WIN"
          export MASSIVE_CHAIN_TRAIL_WINDOW_SEC
          echo "MASSIVE_CHAIN_TRAIL_WINDOW_SEC is now: $MASSIVE_CHAIN_TRAIL_WINDOW_SEC"
        else
          echo "MASSIVE_CHAIN_TRAIL_WINDOW_SEC unchanged."
        fi
        sleep 1
        ;;
      12)
        read -rp "Enter MASSIVE_CHAIN_TRAIL_TTL_SEC (current: $MASSIVE_CHAIN_TRAIL_TTL_SEC): " NEW_TTL
        if [[ -n "$NEW_TTL" ]]; then
          MASSIVE_CHAIN_TRAIL_TTL_SEC="$NEW_TTL"
          export MASSIVE_CHAIN_TRAIL_TTL_SEC
          echo "MASSIVE_CHAIN_TRAIL_TTL_SEC is now: $MASSIVE_CHAIN_TRAIL_TTL_SEC"
        else
          echo "MASSIVE_CHAIN_TRAIL_TTL_SEC unchanged."
        fi
        sleep 1
        ;;
      13)
        echo "Goodbye"
        exit 0
        ;;
      *)
        echo "Invalid choice"
        sleep 1
        ;;
    esac
  done
}

###############################################
# CLI override
###############################################
if [[ $# -gt 0 ]]; then
  case "$1" in
    run) run_foreground ;;
    *)
      echo "Usage: $0 [run]"
      exit 1
      ;;
  esac
else
  menu
fi