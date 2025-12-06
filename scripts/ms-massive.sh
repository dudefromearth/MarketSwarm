#!/opt/homebrew/bin/bash
set -euo pipefail

###############################################
# MarketSwarm MASSIVE – Market Data Engine
###############################################

# Repo root
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE="massive"
MAIN="$ROOT/services/massive/main.py"

VENV="$ROOT/.venv"
VENV_PY="$VENV/bin/python"

# Chain loader path for orchestrator
CHAIN_LOADER="$ROOT/services/massive/utils/massive_chain_loader.py"

BREW_PY="/opt/homebrew/bin/python3.14"
BREW_REDIS="/opt/homebrew/bin/redis-cli"

###############################################
# Redis URLs (system / market / intel)
###############################################
export SYSTEM_REDIS_URL="${SYSTEM_REDIS_URL:-redis://127.0.0.1:6379}"
export MARKET_REDIS_URL="${MARKET_REDIS_URL:-redis://127.0.0.1:6380}"
export INTEL_REDIS_URL="${INTEL_REDIS_URL:-redis://127.0.0.1:6381}"

# Aliases used elsewhere
export REDIS_SYSTEM_URL="$SYSTEM_REDIS_URL"
export REDIS_MARKET_URL="$MARKET_REDIS_URL"

export DEBUG_MASSIVE="${DEBUG_MASSIVE:-false}"

###############################################
# Symbol selection (one symbol per service)
###############################################
export MASSIVE_SYMBOL="${MASSIVE_SYMBOL:-I:SPX}"
ALLOWED_SYMBOLS="I:SPX I:NDX SPY QQQ"

###############################################
# Massive throttling controls
#
# Mental model (one Massive per symbol):
#   - 0DTE expirations:  depth of each snapshot
#   - 0DTE interval:     target time between snapshot *starts*
#                        (0 → as fast as possible)
#   - Rest expirations:  additional expirations beyond 0DTE
#                        (0 → disable rest lane)
#   - Rest interval:     cadence for the rest lane
#   - Max inflight:      max overlapping snapshot cycles
###############################################
export MASSIVE_0DTE_NUM_EXP="${MASSIVE_0DTE_NUM_EXP:-1}"
export MASSIVE_0DTE_INTERVAL_SEC="${MASSIVE_0DTE_INTERVAL_SEC:-1}"
export MASSIVE_REST_NUM_EXP="${MASSIVE_REST_NUM_EXP:-5}"
export MASSIVE_REST_INTERVAL_SEC="${MASSIVE_REST_INTERVAL_SEC:-10}"
export MASSIVE_MAX_INFLIGHT="${MASSIVE_MAX_INFLIGHT:-6}"

# ------------------------------------------------
# 🔥 MASSIVE API KEY — REQUIRED FOR MARKET DATA
# ------------------------------------------------
# truth.workflow.api_key_env = "MASSIVE_API_KEY"
export MASSIVE_API_KEY="pdjraOWSpDbg3ER_RslZYe3dmn4Y7WCC"

# ------------------------------------------------
# Orchestrator wiring
# ------------------------------------------------
export PYTHON_BIN="${PYTHON_BIN:-$VENV_PY}"
export MASSIVE_CHAIN_LOADER="${MASSIVE_CHAIN_LOADER:-$CHAIN_LOADER}"

# SERVICE_ID used by heartbeat / logs
export SERVICE_ID="$SERVICE"

###############################################
# UI Helpers
###############################################
line() { echo "──────────────────────────────────────────────"; }

show_last_chainfeed() {
  clear
  line
  echo " Last 10 Chainfeed Events (sse:chain-feed)"
  line
  echo ""
  $BREW_REDIS -h 127.0.0.1 -p 6380 --raw XREVRANGE sse:chain-feed + - COUNT 10 | sed 's/^/  /'
  echo ""
  read -n 1 -s -r -p "Press any key to return..."
}

configure_symbol() {
  clear
  line
  echo " MASSIVE – Symbol Selection (one symbol per service)"
  line
  echo ""
  echo "Current symbol:"
  echo "  $MASSIVE_SYMBOL"
  echo ""
  echo "Available symbols:"
  echo "  $ALLOWED_SYMBOLS"
  echo ""
  echo "Choose from the list or enter custom:"
  echo "  1) I:SPX"
  echo "  2) I:NDX"
  echo "  3) SPY"
  echo "  4) QQQ"
  echo "  5) Custom input"
  echo ""
  echo "Press ENTER to keep the current value."
  echo ""
  read -rp "Choice [ENTER/1-5]: " CH

  case "$CH" in
    1) MASSIVE_SYMBOL="I:SPX" ;;
    2) MASSIVE_SYMBOL="I:NDX" ;;
    3) MASSIVE_SYMBOL="SPY" ;;
    4) MASSIVE_SYMBOL="QQQ" ;;
    5)
      read -rp "Enter custom symbol [${MASSIVE_SYMBOL}]: " SYM
      if [[ -n "$SYM" ]]; then
        MASSIVE_SYMBOL="$SYM"
      fi
      ;;
    "" ) ;;
    * )
      echo "Invalid choice, keeping current symbol."
      sleep 1
      ;;
  esac

  echo ""
  line
  echo "Updated symbol:"
  echo "  $MASSIVE_SYMBOL"
  line
  echo ""
  read -n 1 -s -r -p "Press any key to return to main menu..."
}

configure_throttling() {
  clear
  line
  echo " MASSIVE – DTE Throttling Configuration"
  line
  echo ""
  echo "Meaning of knobs (per Massive instance):"
  echo "  • 0DTE expirations  → expirations per snapshot (depth)"
  echo "  • 0DTE interval     → seconds between snapshot starts (0 = as fast as possible)"
  echo "  • Rest expirations  → extra expirations beyond 0DTE (0 = disable rest lane)"
  echo "  • Rest interval     → seconds between rest-lane cycles"
  echo "  • Max inflight      → max overlapping snapshot cycles"
  echo ""
  echo "Current settings (symbol: $MASSIVE_SYMBOL):"
  echo "  0DTE expirations:      $MASSIVE_0DTE_NUM_EXP"
  echo "  0DTE interval (sec):   $MASSIVE_0DTE_INTERVAL_SEC"
  echo "  Rest expirations:      $MASSIVE_REST_NUM_EXP"
  echo "  Rest interval (sec):   $MASSIVE_REST_INTERVAL_SEC"
  echo "  Max inflight cycles:   $MASSIVE_MAX_INFLIGHT"
  echo ""
  echo "Press ENTER to keep the current value."
  echo ""

  local input

  read -rp "0DTE # of expirations [${MASSIVE_0DTE_NUM_EXP}]: " input
  if [[ -n "$input" ]]; then
    MASSIVE_0DTE_NUM_EXP="$input"
  fi

  read -rp "0DTE interval seconds [${MASSIVE_0DTE_INTERVAL_SEC}]: " input
  if [[ -n "$input" ]]; then
    MASSIVE_0DTE_INTERVAL_SEC="$input"
  fi

  read -rp "Rest # of expirations [${MASSIVE_REST_NUM_EXP}]: " input
  if [[ -n "$input" ]]; then
    MASSIVE_REST_NUM_EXP="$input"
  fi

  read -rp "Rest interval seconds [${MASSIVE_REST_INTERVAL_SEC}]: " input
  if [[ -n "$input" ]]; then
    MASSIVE_REST_INTERVAL_SEC="$input"
  fi

  read -rp "Max inflight cycles [${MASSIVE_MAX_INFLIGHT}]: " input
  if [[ -n "$input" ]]; then
    MASSIVE_MAX_INFLIGHT="$input"
  fi

  echo ""
  line
  echo "Updated throttling (symbol: $MASSIVE_SYMBOL):"
  echo "  0DTE expirations:      $MASSIVE_0DTE_NUM_EXP"
  echo "  0DTE interval (sec):   $MASSIVE_0DTE_INTERVAL_SEC"
  echo "  Rest expirations:      $MASSIVE_REST_NUM_EXP"
  echo "  Rest interval (sec):   $MASSIVE_REST_INTERVAL_SEC"
  echo "  Max inflight cycles:   $MASSIVE_MAX_INFLIGHT"
  line
  echo ""
  read -n 1 -s -r -p "Press any key to return to main menu..."
}

###############################################
# Main Menu
###############################################
menu() {
  clear
  line
  echo " MarketSwarm – MASSIVE Market Data Engine"
  line
  echo "Select Option:"
  echo ""
  echo "  1) RUN Massive"
  echo "  2) View Last 10 Chainfeed Entries"
  echo "  3) Configure Symbol"
  echo "  4) Configure DTE Throttling"
  echo "  5) Quit"
  echo ""
  echo "Current symbol:"
  echo "  $MASSIVE_SYMBOL"
  echo ""
  echo "Current throttling:"
  echo "  0DTE: ${MASSIVE_0DTE_NUM_EXP} exp(s) every ${MASSIVE_0DTE_INTERVAL_SEC}s"
  echo "  Rest: ${MASSIVE_REST_NUM_EXP} exp(s) every ${MASSIVE_REST_INTERVAL_SEC}s"
  echo "  Max inflight cycles: ${MASSIVE_MAX_INFLIGHT}"
  echo ""
  line
  read -rp "Enter choice [1-5]: " CH
  echo ""

  case "$CH" in
    1)  ;; # Continue to run
    2)  show_last_chainfeed; menu ;;
    3)  configure_symbol; menu ;;
    4)  configure_throttling; menu ;;
    5)  echo "Goodbye"; exit 0 ;;
    *)  echo "Invalid"; sleep 1; menu ;;
  esac
}

###############################################
# Argument override
###############################################
if [[ $# -gt 0 ]]; then
  case "$1" in
    run) ;;       # default, just run with current env
    show) show_last_chainfeed; exit 0 ;;
    debug) export DEBUG_MASSIVE="true" ;;
    *)
      echo "Usage: $0 [run|show|debug]"
      exit 1
      ;;
  esac
else
  menu
fi

###############################################
# Map menu throttling → scheduler env for setup.py
###############################################
export MASSIVE_FAST_NUM_EXPIRATIONS="$MASSIVE_0DTE_NUM_EXP"
export MASSIVE_FAST_INTERVAL_SEC="$MASSIVE_0DTE_INTERVAL_SEC"
export MASSIVE_REST_NUM_EXPIRATIONS="$MASSIVE_REST_NUM_EXP"
export MASSIVE_REST_INTERVAL_SEC="$MASSIVE_REST_INTERVAL_SEC"
# Max inflight directly read by setup.py
export MASSIVE_MAX_INFLIGHT="$MASSIVE_MAX_INFLIGHT"

###############################################
# Bootstrap & Validation
###############################################
line
echo " MASSIVE Service Runner (Brew)"
line
echo "ROOT: $ROOT"
[[ "$DEBUG_MASSIVE" == "true" ]] && echo "DEBUG: enabled"
echo "MASSIVE_API_KEY: (set)"
echo "MASSIVE_SYMBOL:        $MASSIVE_SYMBOL"
echo "SYSTEM_REDIS_URL:      $SYSTEM_REDIS_URL"
echo "MARKET_REDIS_URL:      $MARKET_REDIS_URL"
echo "INTEL_REDIS_URL:       $INTEL_REDIS_URL"
echo "PYTHON_BIN:            $PYTHON_BIN"
echo "MASSIVE_CHAIN_LOADER:  $MASSIVE_CHAIN_LOADER"
echo "0DTE expirations:      $MASSIVE_0DTE_NUM_EXP"
echo "0DTE interval (sec):   $MASSIVE_0DTE_INTERVAL_SEC"
echo "Rest expirations:      $MASSIVE_REST_NUM_EXP"
echo "Rest interval (sec):   $MASSIVE_REST_INTERVAL_SEC"
echo "Max inflight cycles:   $MASSIVE_MAX_INFLIGHT"
echo ""

for cmd in "$BREW_PY" "$VENV_PY" "$BREW_REDIS"; do
  if [[ -x "$cmd" ]]; then
    echo "Found $cmd"
  else
    echo "Missing $cmd"
    exit 1
  fi
done

HAS_TRUTH=$($BREW_REDIS -h 127.0.0.1 -p 6379 EXISTS truth)
if [[ "$HAS_TRUTH" -eq 1 ]]; then
  echo "Truth found"
else
  echo "Missing truth"
  exit 1
fi

###############################################
# Launch MASSIVE
###############################################
line
echo "Launching MASSIVE for symbol: $MASSIVE_SYMBOL"
line

exec "$VENV_PY" "$MAIN"