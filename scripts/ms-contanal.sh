#!/opt/homebrew/bin/bash
set -euo pipefail

###############################################
# MarketSwarm – Content Analysis Engine
# Modeled on ms-vigil.sh, ms-vexyai.sh, ms-rssagg.sh
###############################################

# Environment
export SYSTEM_REDIS_URL="redis://127.0.0.1:6379"
export MARKET_REDIS_URL="redis://127.0.0.1:6380"
export INTEL_REDIS_URL="redis://127.0.0.1:6381"

export DEBUG_CONTANAL="${DEBUG_CONTANAL:-false}"

BREW_PY="/opt/homebrew/bin/python3.14"
BREW_REDIS="/opt/homebrew/bin/redis-cli"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE="content_anal"
MAIN="$ROOT/services/content_anal/main.py"

VENV="$ROOT/.venv"
VENV_PY="$VENV/bin/python"

###############################################
# UI Helpers
###############################################
line() { echo "──────────────────────────────────────────────"; }

show_last_outputs() {
  clear
  line
  echo " Last 10 Content_Anal Synthetic Outputs (content_anal:outbox)"
  line
  echo ""

  $BREW_REDIS -h 127.0.0.1 -p 6381 --csv XREVRANGE content_anal:outbox + - COUNT 10 | \
    jq -r '.[] | [.[0], (.[1] | fromjson | .item | fromjson | .title)] | join(" | ")'

  echo ""
  read -n 1 -s -r -p "Press any key to return..."
}

###############################################
# Main Menu
###############################################
menu() {
  clear
  line
  echo " MarketSwarm – Content Analysis Engine"
  line
  echo "Select Option:"
  echo ""
  echo "  1) RUN Content_Anal"
  echo "  2) View Last 10 Synthetic Items"
  echo "  3) Quit"
  echo ""
  line
  read -rp "Enter choice [1-3]: " CH
  echo ""

  case "$CH" in
    1) ;;  # proceed to run
    2) show_last_outputs; menu ;;
    3) echo "Goodbye"; exit 0 ;;
    *) echo "Invalid"; sleep 1; menu ;;
  esac
}

###############################################
# Argument override
###############################################
if [[ $# -gt 0 ]]; then
  case "$1" in
    run) ;;  # fall through to launch
    show) show_last_outputs; exit 0 ;;
    debug) export DEBUG_CONTANAL="true" ;;
    *)
      echo "Usage: $0 [run|show|debug]"
      exit 1
      ;;
  esac
else
  menu
fi

###############################################
# Bootstrap & Validation
###############################################
line
echo " Content_Anal Service Runner (Brew)"
line
echo "ROOT: $ROOT"
[[ "$DEBUG_CONTANAL" == "true" ]] && echo "DEBUG: enabled"
echo ""

# Validate tools
for cmd in "$BREW_PY" "$VENV_PY" "$BREW_REDIS"; do
  [[ -x "$cmd" ]] && echo "Found $cmd" || { echo "Missing $cmd"; exit 1; }
done

# Validate truth
HAS_TRUTH=$($BREW_REDIS -h 127.0.0.1 -p 6379 EXISTS truth)
[[ "$HAS_TRUTH" -eq 1 ]] && echo "Truth found" || { echo "Missing truth"; exit 1; }

###############################################
# Launch Content Analysis Engine
###############################################
line
echo "Launching Content_Anal"
line

export SERVICE_ID="$SERVICE"
exec "$VENV_PY" "$MAIN"