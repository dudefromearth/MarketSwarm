#!/opt/homebrew/bin/bash
set -euo pipefail

###############################################
# MarketSwarm Vigil – Event Watcher
# (Modeled on ms-vexyai.sh and ms-rssagg.sh)
###############################################

# Environment
export SYSTEM_REDIS_URL="redis://127.0.0.1:6379"
export MARKET_REDIS_URL="redis://127.0.0.1:6380"
export INTEL_REDIS_URL="redis://127.0.0.1:6381"

export DEBUG_VIGIL="${DEBUG_VIGIL:-false}"      # verbose logging

BREW_PY="/opt/homebrew/bin/python3.14"
BREW_REDIS="/opt/homebrew/bin/redis-cli"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE="vigil"
MAIN="$ROOT/services/vigil/main.py"

VENV="$ROOT/.venv"
VENV_PY="$VENV/bin/python"

###############################################
# UI Helpers
###############################################
line() { echo "──────────────────────────────────────────────"; }

show_last_events() {
  clear
  line
  echo " Last 10 Vigil Events (vigil:events)"
  line
  echo ""

  $BREW_REDIS -h 127.0.0.1 -p 6380 --csv XREVRANGE vigil:events + - COUNT 10 | \
    jq -r '.[] | [.[0], (.[1] | fromjson | .event | fromjson | .type)] | join(" | ")'

  echo ""
  read -n 1 -s -r -p "Press any key to return..."
}

###############################################
# Main Menu
###############################################
menu() {
  clear
  line
  echo " MarketSwarm – Vigil Event Watcher"
  line
  echo "Select Option:"
  echo ""
  echo "  1) RUN Vigil"
  echo "  2) View Last 10 Events"
  echo "  3) Quit"
  echo ""
  line
  read -rp "Enter choice [1-3]: " CH
  echo ""

  case "$CH" in
    1)  ;;  # proceed to run
    2)  show_last_events; menu ;;
    3)  echo "Goodbye"; exit 0 ;;
    *)  echo "Invalid"; sleep 1; menu ;;
  esac
}

###############################################
# Argument override (same as others)
###############################################
if [[ $# -gt 0 ]]; then
  case "$1" in
    run)  ;;    # let it fall through to launch
    show) show_last_events; exit 0 ;;
    debug) export DEBUG_VIGIL="true" ;;
    *) echo "Usage: $0 [run|show|debug]"; exit 1 ;;
  esac
else
  menu
fi

###############################################
# Bootstrap & Validation
###############################################
line
echo " Vigil Service Runner (Brew)"
line
echo "ROOT: $ROOT"
[[ "$DEBUG_VIGIL" == "true" ]] && echo "DEBUG: enabled"
echo ""

# Validate tools
for cmd in "$BREW_PY" "$VENV_PY" "$BREW_REDIS"; do
  [[ -x "$cmd" ]] && echo "Found $cmd" || { echo "Missing $cmd"; exit 1; }
done

# Validate truth
HAS_TRUTH=$($BREW_REDIS -h 127.0.0.1 -p 6379 EXISTS truth)
[[ "$HAS_TRUTH" -eq 1 ]] && echo "Truth found" || { echo "Missing truth"; exit 1; }

###############################################
# Launch Vigil
###############################################
line
echo "Launching Vigil Event Watcher"
line

export SERVICE_ID="$SERVICE"
exec "$VENV_PY" "$MAIN"