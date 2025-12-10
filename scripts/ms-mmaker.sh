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

# mmaker-specific: Stub for expiry/underlying (set in main/setup if dynamic; override via env)
export MMAKER_EXPIRY_YYYYMMDD="${MMAKER_EXPIRY_YYYYMMDD:-20251209}"
export MMAKER_UNDERLYING="${MMAKER_UNDERLYING:-SPX}"

BREW_PY="/opt/homebrew/bin/python3.14"  # Fallback to /usr/bin/python3 on Linux if needed
if [[ ! -x "$BREW_PY" ]]; then BREW_PY="/usr/bin/python3"; fi

BREW_REDIS="/opt/homebrew/bin/redis-cli"
if [[ ! -x "$BREW_REDIS" ]]; then BREW_REDIS="/usr/bin/redis-cli"; fi

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

bootstrap_venv() {
  if [[ ! -d "$VENV" ]]; then
    echo "Creating venv at $VENV..."
    "$BREW_PY" -m venv "$VENV"
  fi
  if [[ ! -f "$VENV/bin/requirements.txt" ]]; then  # Assume requirements.txt in ROOT
    echo "Installing deps (assume requirements.txt in $ROOT)..."
    "$VENV_PY" -m pip install --upgrade pip
    "$VENV_PY" -m pip install -r "$ROOT/requirements.txt"  # Adjust if pip-sync
  fi
}

run_foreground() {
  # Early checks
  if [[ ! -f "$MAIN" ]]; then
    echo "ERROR: Main script missing: $MAIN"
    exit 1
  fi
  bootstrap_venv

  clear
  line
  echo " Launching $SERVICE (foreground)"
  line
  echo "ROOT:         $ROOT"
  echo "SERVICE_ID:   $SERVICE"
  echo "VENV_PY:      $VENV_PY"
  echo "MAIN:         $MAIN"
  echo "DEBUG_MMAKER: $DEBUG_MMAKER"
  echo "EXPIRY:       $MMAKER_EXPIRY_YYYYMMDD"
  echo "UNDERLYING:   $MMAKER_UNDERLYING"
  line
  echo ""

  check_tools
  echo ""
  echo "Running $SERVICE in foreground. Ctrl+C to stop."
  echo ""

  cd "$ROOT"
  export SERVICE_ID="$SERVICE"
  export DEBUG_MMAKER
  export MMAKER_EXPIRY_YYYYMMDD
  export MMAKER_UNDERLYING

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
    echo "  EXPIRY       = $MMAKER_EXPIRY_YYYYMMDD"
    echo "  UNDERLYING   = $MMAKER_UNDERLYING"
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