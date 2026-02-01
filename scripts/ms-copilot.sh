#!/opt/homebrew/bin/bash
set -euo pipefail

###############################################
# MarketSwarm – Copilot Service
# MEL + ADI + Commentary + Alerts
###############################################

BREW_PY="/opt/homebrew/bin/python3.14"
BREW_REDIS="/opt/homebrew/bin/redis-cli"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE="copilot"
MAIN="$ROOT/services/copilot/main.py"

VENV="$ROOT/.venv"
VENV_PY="$VENV/bin/python"

# Environment - Redis
export SYSTEM_REDIS_URL="redis://127.0.0.1:6379"
export MARKET_REDIS_URL="redis://127.0.0.1:6380"

# AI Provider Keys (required for Commentary and AI Alerts)
export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}"
export OPENAI_API_KEY="${OPENAI_API_KEY:-}"

# Copilot config (can be overridden)
export COPILOT_PORT="${COPILOT_PORT:-8095}"
export COPILOT_MEL_ENABLED="${COPILOT_MEL_ENABLED:-true}"
export COPILOT_ADI_ENABLED="${COPILOT_ADI_ENABLED:-true}"
export COPILOT_COMMENTARY_ENABLED="${COPILOT_COMMENTARY_ENABLED:-false}"
export COPILOT_ALERTS_ENABLED="${COPILOT_ALERTS_ENABLED:-true}"
export DEBUG_COPILOT="${DEBUG_COPILOT:-false}"

###############################################
# UI Helpers
###############################################
line() { echo "──────────────────────────────────────────────"; }

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

status_indicator() {
  if [[ "$1" == "true" ]]; then
    echo -e "${GREEN}●${NC}"
  else
    echo -e "${RED}○${NC}"
  fi
}

show_status() {
  clear
  line
  echo " Copilot Service Status"
  line
  echo ""
  echo "  MEL:        $(status_indicator $COPILOT_MEL_ENABLED) $COPILOT_MEL_ENABLED"
  echo "  ADI:        $(status_indicator $COPILOT_ADI_ENABLED) $COPILOT_ADI_ENABLED"
  echo "  Commentary: $(status_indicator $COPILOT_COMMENTARY_ENABLED) $COPILOT_COMMENTARY_ENABLED"
  echo "  Alerts:     $(status_indicator $COPILOT_ALERTS_ENABLED) $COPILOT_ALERTS_ENABLED"
  echo ""
  echo "  Port:       $COPILOT_PORT"
  echo "  Debug:      $DEBUG_COPILOT"
  echo ""

  # Check API keys
  if [[ -n "$ANTHROPIC_API_KEY" ]]; then
    echo -e "  Anthropic:  ${GREEN}configured${NC}"
  else
    echo -e "  Anthropic:  ${YELLOW}not set${NC}"
  fi
  if [[ -n "$OPENAI_API_KEY" ]]; then
    echo -e "  OpenAI:     ${GREEN}configured${NC}"
  else
    echo -e "  OpenAI:     ${YELLOW}not set${NC}"
  fi
  echo ""

  # Check if running
  if lsof -i:$COPILOT_PORT &>/dev/null; then
    echo -e "  Service:    ${GREEN}RUNNING${NC}"
  else
    echo -e "  Service:    ${RED}STOPPED${NC}"
  fi

  echo ""
  line
  read -n 1 -s -r -p "Press any key to return..."
}

show_latest_alerts() {
  clear
  line
  echo " Latest Alert Events"
  line
  echo ""

  ALERT_RAW=$($BREW_REDIS -h 127.0.0.1 -p 6380 GET "copilot:alerts:latest" 2>/dev/null)
  if [[ -n "$ALERT_RAW" && "$ALERT_RAW" != "nil" ]]; then
    echo "$ALERT_RAW" | jq '.' 2>/dev/null || echo "$ALERT_RAW"
  else
    echo "  (no alerts)"
  fi

  echo ""
  line
  read -n 1 -s -r -p "Press any key to return..."
}

###############################################
# Main Menu
###############################################
menu() {
  clear
  line
  echo " MarketSwarm – Copilot Service"
  echo " MEL + ADI + Commentary + Alerts"
  line
  echo ""
  echo "  Current Config:"
  echo "    MEL: $COPILOT_MEL_ENABLED | ADI: $COPILOT_ADI_ENABLED"
  echo "    Commentary: $COPILOT_COMMENTARY_ENABLED | Alerts: $COPILOT_ALERTS_ENABLED"
  echo ""
  echo "  Select Mode:"
  echo ""
  echo "  1) Full (all features)"
  echo "  2) MEL + ADI only"
  echo "  3) MEL only"
  echo "  4) Enable Commentary"
  echo "  5) Enable Alerts"
  echo "  6) Disable Alerts"
  echo ""
  echo "  7) View Status"
  echo "  8) View Latest Alerts"
  echo "  9) Debug Mode"
  echo ""
  echo "  r) Run Service"
  echo "  q) Quit"
  line
  read -rp "Enter choice: " CH
  echo ""

  case "$CH" in
    1)
      export COPILOT_MEL_ENABLED="true"
      export COPILOT_ADI_ENABLED="true"
      export COPILOT_COMMENTARY_ENABLED="true"
      export COPILOT_ALERTS_ENABLED="true"
      ;;
    2)
      export COPILOT_MEL_ENABLED="true"
      export COPILOT_ADI_ENABLED="true"
      export COPILOT_COMMENTARY_ENABLED="false"
      export COPILOT_ALERTS_ENABLED="false"
      ;;
    3)
      export COPILOT_MEL_ENABLED="true"
      export COPILOT_ADI_ENABLED="false"
      export COPILOT_COMMENTARY_ENABLED="false"
      export COPILOT_ALERTS_ENABLED="false"
      ;;
    4)
      export COPILOT_COMMENTARY_ENABLED="true"
      ;;
    5)
      export COPILOT_ALERTS_ENABLED="true"
      ;;
    6)
      export COPILOT_ALERTS_ENABLED="false"
      ;;
    7) show_status; menu ;;
    8) show_latest_alerts; menu ;;
    9)
      export DEBUG_COPILOT="true"
      echo "Debug mode enabled"
      ;;
    r|R) return 0 ;;
    q|Q) echo "Goodbye"; exit 0 ;;
    *) echo "Invalid choice"; sleep 1 ;;
  esac
  menu
}

###############################################
# Argument handling (CLI mode)
###############################################
if [[ $# -gt 0 ]]; then
  case "$1" in
    run|start)
      # Just run with current settings
      ;;
    debug)
      export DEBUG_COPILOT="true"
      ;;
    port)
      export COPILOT_PORT="${2:-8095}"
      ;;
    full)
      export COPILOT_MEL_ENABLED="true"
      export COPILOT_ADI_ENABLED="true"
      export COPILOT_COMMENTARY_ENABLED="true"
      export COPILOT_ALERTS_ENABLED="true"
      ;;
    mel-only)
      export COPILOT_MEL_ENABLED="true"
      export COPILOT_ADI_ENABLED="false"
      export COPILOT_COMMENTARY_ENABLED="false"
      export COPILOT_ALERTS_ENABLED="false"
      ;;
    mel-adi)
      export COPILOT_MEL_ENABLED="true"
      export COPILOT_ADI_ENABLED="true"
      export COPILOT_COMMENTARY_ENABLED="false"
      export COPILOT_ALERTS_ENABLED="false"
      ;;
    alerts)
      export COPILOT_ALERTS_ENABLED="true"
      ;;
    no-alerts)
      export COPILOT_ALERTS_ENABLED="false"
      ;;
    commentary)
      export COPILOT_COMMENTARY_ENABLED="true"
      ;;
    status)
      show_status
      exit 0
      ;;
    help|-h|--help)
      echo "Usage: $0 [command] [options]"
      echo ""
      echo "Commands:"
      echo "  run           Run with current settings"
      echo "  debug         Enable debug logging"
      echo "  port <num>    Override default port (8095)"
      echo "  full          Enable all features"
      echo "  mel-only      Only enable MEL"
      echo "  mel-adi       Enable MEL + ADI only"
      echo "  alerts        Enable alerts"
      echo "  no-alerts     Disable alerts"
      echo "  commentary    Enable AI commentary"
      echo "  status        Show current status"
      echo ""
      echo "Without arguments, shows interactive menu."
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      echo "Run '$0 help' for usage"
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
echo " Copilot Service Runner"
line
echo "ROOT: $ROOT"
echo "PORT: $COPILOT_PORT"
echo ""
echo "Features:"
echo "  MEL:        $COPILOT_MEL_ENABLED"
echo "  ADI:        $COPILOT_ADI_ENABLED"
echo "  Commentary: $COPILOT_COMMENTARY_ENABLED"
echo "  Alerts:     $COPILOT_ALERTS_ENABLED"
[[ "$DEBUG_COPILOT" == "true" ]] && echo "  DEBUG:      enabled"
echo ""

# Warn about missing API keys for AI features
if [[ "$COPILOT_COMMENTARY_ENABLED" == "true" || "$COPILOT_ALERTS_ENABLED" == "true" ]]; then
  if [[ -z "$ANTHROPIC_API_KEY" && -z "$OPENAI_API_KEY" ]]; then
    echo -e "${YELLOW}[WARN]${NC} AI features enabled but no API key set"
    echo "       Set ANTHROPIC_API_KEY or OPENAI_API_KEY"
    echo ""
  fi
fi

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
echo "Launching Copilot Service"
line

export SERVICE_ID="$SERVICE"
exec "$VENV_PY" "$MAIN"
