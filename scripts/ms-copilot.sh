#!/opt/homebrew/bin/bash
set -euo pipefail

###############################################
# MarketSwarm – Copilot Service
# MEL + ADI + AI Commentary
###############################################

BREW_PY="/opt/homebrew/bin/python3.14"
BREW_REDIS="/opt/homebrew/bin/redis-cli"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE="copilot"
MAIN="$ROOT/services/copilot/main.py"

VENV="$ROOT/.venv"
VENV_PY="$VENV/bin/python"

# Environment
export SYSTEM_REDIS_URL="redis://127.0.0.1:6379"
export MARKET_REDIS_URL="redis://127.0.0.1:6380"

# Copilot config (can be overridden)
export COPILOT_PORT="${COPILOT_PORT:-8095}"
export COPILOT_MEL_ENABLED="${COPILOT_MEL_ENABLED:-true}"
export COPILOT_ADI_ENABLED="${COPILOT_ADI_ENABLED:-true}"
export COPILOT_COMMENTARY_ENABLED="${COPILOT_COMMENTARY_ENABLED:-false}"
export DEBUG_COPILOT="${DEBUG_COPILOT:-false}"

###############################################
# UI Helpers
###############################################
line() { echo "──────────────────────────────────────────────"; }

###############################################
# Argument handling
###############################################
if [[ $# -gt 0 ]]; then
  case "$1" in
    debug)    export DEBUG_COPILOT="true" ;;
    port)     export COPILOT_PORT="${2:-8095}" ;;
    mel-only)
      export COPILOT_MEL_ENABLED="true"
      export COPILOT_ADI_ENABLED="false"
      export COPILOT_COMMENTARY_ENABLED="false"
      ;;
    commentary)
      export COPILOT_COMMENTARY_ENABLED="true"
      ;;
    help|-h)
      echo "Usage: $0 [debug|port <num>|mel-only|commentary]"
      echo ""
      echo "Options:"
      echo "  debug        Enable debug logging"
      echo "  port <num>   Override default port (8095)"
      echo "  mel-only     Only enable MEL (disable ADI/Commentary)"
      echo "  commentary   Enable AI Commentary (requires API key)"
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
echo " MarketSwarm – Copilot Service (MEL + ADI)"
line
echo "ROOT: $ROOT"
echo "PORT: $COPILOT_PORT"
echo "MEL:  $COPILOT_MEL_ENABLED"
echo "ADI:  $COPILOT_ADI_ENABLED"
echo "COMMENTARY: $COPILOT_COMMENTARY_ENABLED"
[[ "$DEBUG_COPILOT" == "true" ]] && echo "DEBUG: enabled"
echo ""

# Validate tools
for cmd in "$VENV_PY" "$BREW_REDIS"; do
  [[ -x "$cmd" ]] && echo "Found $cmd" || { echo "Missing $cmd"; exit 1; }
done

# Validate truth
HAS_TRUTH=$($BREW_REDIS -h 127.0.0.1 -p 6379 EXISTS truth)
[[ "$HAS_TRUTH" -eq 1 ]] && echo "Truth found" || { echo "Missing truth"; exit 1; }

###############################################
# Launch Copilot
###############################################
line
echo "Launching Copilot Service (PORT=$COPILOT_PORT)"
line

export SERVICE_ID="$SERVICE"
exec "$VENV_PY" "$MAIN"
