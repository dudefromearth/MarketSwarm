#!/opt/homebrew/bin/bash
set -euo pipefail

###############################################
# MarketSwarm – mmaker (Redis Model Engine)
# Foreground dev runner (no PID, no log file)
###############################################

# ------------------------------------------------
# Environment
# ------------------------------------------------
export SYSTEM_REDIS_URL="redis://127.0.0.1:6379"
export MARKET_REDIS_URL="redis://127.0.0.1:6380"
export INTEL_REDIS_URL="redis://127.0.0.1:6381"

export DEBUG_MMAKER="${DEBUG_MMAKER:-false}"

BREW_PY="/opt/homebrew/bin/python3.14"
BREW_REDIS="/opt/homebrew/bin/redis-cli"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE="mmaker"
MAIN="$ROOT/services/mmaker/main.py"

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
  echo "ROOT:         $ROOT"
  echo "SERVICE_ID:   $SERVICE"
  echo "VENV_PY:      $VENV_PY"
  echo "MAIN:         $MAIN"
  echo "DEBUG_MMAKER: $DEBUG_MMAKER"
  line
  echo ""

  check_tools
  echo ""
  echo "Running $SERVICE in foreground. Ctrl+C to stop."
  echo ""

  cd "$ROOT"
  export SERVICE_ID="$SERVICE"
  export DEBUG_MMAKER

  # Exec in the foreground so stdout/stderr go directly to the terminal
  exec "$VENV_PY" "$MAIN"
}

###############################################
# Menu
###############################################
menu() {
  while true; do
    clear
    line
    echo " MarketSwarm – mmaker (Redis Model Engine)"
    line
    echo ""
    echo "Current configuration:"
    echo "  DEBUG_MMAKER = $DEBUG_MMAKER"
    echo ""
    echo "Select Option:"
    echo ""
    echo "  1) Run mmaker (foreground)"
    echo "  2) Toggle DEBUG_MMAKER"
    echo "  3) Quit"
    echo ""
    line
    read -rp "Enter choice [1-3]: " CH
    echo ""

    case "$CH" in
      1) run_foreground ;;  # exec, doesn't return
      2)
        if [[ "$DEBUG_MMAKER" == "true" ]]; then
          DEBUG_MMAKER="false"
        else
          DEBUG_MMAKER="true"
        fi
        export DEBUG_MMAKER
        echo "DEBUG_MMAKER is now: $DEBUG_MMAKER"
        sleep 1
        ;;
      3) echo "Goodbye"; exit 0 ;;
      *) echo "Invalid choice"; sleep 1 ;;
    esac
  done
}

###############################################
# CLI override
###############################################
if [[ $# -gt 0 ]]; then
  case "$1" in
    run) run_foreground ;;  # no menu, just run
    *)
      echo "Usage: $0 [run]"
      exit 1
      ;;
  esac
else
  menu
fi