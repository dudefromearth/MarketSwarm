#!/opt/homebrew/bin/bash
set -euo pipefail

###############################################
# MarketSwarm – mesh (Mesh Coordinator)
# Foreground dev runner (no PID, no log file)
###############################################

# ------------------------------------------------
# Environment
# ------------------------------------------------
export SYSTEM_REDIS_URL="redis://127.0.0.1:6379"
export MARKET_REDIS_URL="redis://127.0.0.1:6380"
export INTEL_REDIS_URL="redis://127.0.0.1:6381"

export DEBUG_MESH="${DEBUG_MESH:-false}"

BREW_PY="/opt/homebrew/bin/python3.14"
BREW_REDIS="/opt/homebrew/bin/redis-cli"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE="mesh"
MAIN="$ROOT/services/mesh/main.py"

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
  echo "ROOT:       $ROOT"
  echo "SERVICE_ID: $SERVICE"
  echo "VENV_PY:    $VENV_PY"
  echo "MAIN:       $MAIN"
  echo "DEBUG_MESH: $DEBUG_MESH"
  line
  echo ""

  check_tools
  echo ""
  echo "Running $SERVICE in foreground. Ctrl+C to stop."
  echo ""

  cd "$ROOT"
  export SERVICE_ID="$SERVICE"
  export DEBUG_MESH

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
    echo " MarketSwarm – mesh (Mesh Coordinator)"
    line
    echo ""
    echo "Current configuration:"
    echo "  DEBUG_MESH = $DEBUG_MESH"
    echo ""
    echo "Select Option:"
    echo ""
    echo "  1) Run mesh (foreground)"
    echo "  2) Toggle DEBUG_MESH"
    echo "  3) Quit"
    echo ""
    line
    read -rp "Enter choice [1-3]: " CH
    echo ""

    case "$CH" in
      1) run_foreground ;;  # exec, doesn't return
      2)
        if [[ "$DEBUG_MESH" == "true" ]]; then
          DEBUG_MESH="false"
        else
          DEBUG_MESH="true"
        fi
        export DEBUG_MESH
        echo "DEBUG_MESH is now: $DEBUG_MESH"
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