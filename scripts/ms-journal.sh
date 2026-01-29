#!/opt/homebrew/bin/bash
set -euo pipefail

###############################################
# MarketSwarm – Journal Service
# Trade logging, journaling, and analytics
###############################################

BREW_PY="/opt/homebrew/bin/python3.14"
BREW_REDIS="/opt/homebrew/bin/redis-cli"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE="journal"
MAIN="$ROOT/services/journal/main.py"

VENV="$ROOT/.venv"
VENV_PY="$VENV/bin/python"

# Environment
export SYSTEM_REDIS_URL="redis://127.0.0.1:6379"
export MARKET_REDIS_URL="redis://127.0.0.1:6380"

# Journal config (can be overridden)
export JOURNAL_PORT="${JOURNAL_PORT:-3002}"
export DEBUG_JOURNAL="${DEBUG_JOURNAL:-false}"

###############################################
# UI Helpers
###############################################
line() { echo "──────────────────────────────────────────────"; }

###############################################
# Argument handling
###############################################
if [[ $# -gt 0 ]]; then
  case "$1" in
    debug)    export DEBUG_JOURNAL="true" ;;
    port)     export JOURNAL_PORT="${2:-3002}" ;;
    help|-h)
      echo "Usage: $0 [debug|port <num>]"
      echo ""
      echo "Options:"
      echo "  debug        Enable debug logging"
      echo "  port <num>   Override default port (3002)"
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      echo "Run '$0 help' for usage"
      exit 1
      ;;
  esac
fi

###############################################
# Bootstrap & Validation
###############################################
line
echo " MarketSwarm – Journal Service"
line
echo "ROOT: $ROOT"
echo "PORT: $JOURNAL_PORT"
[[ "$DEBUG_JOURNAL" == "true" ]] && echo "DEBUG: enabled"
echo ""

# Validate tools
for cmd in "$VENV_PY" "$BREW_REDIS"; do
  [[ -x "$cmd" ]] && echo "Found $cmd" || { echo "Missing $cmd"; exit 1; }
done

# Validate truth
HAS_TRUTH=$($BREW_REDIS -h 127.0.0.1 -p 6379 EXISTS truth)
[[ "$HAS_TRUTH" -eq 1 ]] && echo "Truth found" || { echo "Missing truth"; exit 1; }

###############################################
# Launch Journal
###############################################
line
echo "Launching Journal Service (PORT=$JOURNAL_PORT)"
line

export SERVICE_ID="$SERVICE"
exec "$VENV_PY" "$MAIN"
