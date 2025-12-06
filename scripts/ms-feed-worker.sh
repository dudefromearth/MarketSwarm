#!/opt/homebrew/bin/bash
set -euo pipefail

###############################################
# MarketSwarm – feed_worker (DTE Feed Worker)
# Foreground dev runner (no PID, no log file)
###############################################

# ------------------------------------------------
# Core Redis URLs (shared with other services)
# ------------------------------------------------
export SYSTEM_REDIS_URL="${SYSTEM_REDIS_URL:-redis://127.0.0.1:6379}"
export MARKET_REDIS_URL="${MARKET_REDIS_URL:-redis://127.0.0.1:6380}"
export INTEL_REDIS_URL="${INTEL_REDIS_URL:-redis://127.0.0.1:6381}"

# This worker writes to MARKET_REDIS_URL.
# dte_feed_worker.py uses REDIS_HOST/PORT/DB, so we derive them here.
export REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
export REDIS_PORT="${REDIS_PORT:-6380}"
export REDIS_DB="${REDIS_DB:-0}"

# ------------------------------------------------
# Polygon / symbol config (worker-specific)
# ------------------------------------------------
# IMPORTANT: POLYGON_API_KEY must be set in your shell/env.
export POLYGON_API_KEY="${POLYGON_API_KEY:-}"

# API index symbol (Polygon) and display/Redis symbol
export API_SYMBOL="${API_SYMBOL:-I:SPX}"
export SYMBOL="${SYMBOL:-SPX}"

# DTEs to poll (comma-separated list)
export DTE_LIST="${DTE_LIST:-0,1,2,3,4,5}"

# ------------------------------------------------
# Snapshot / trails / cadence
# ------------------------------------------------
export TRAIL_TTL_SECONDS="${TRAIL_TTL_SECONDS:-1200}"
export SNAPSHOT_TTL_SECONDS="${SNAPSHOT_TTL_SECONDS:-259200}"   # 3 days = 3*24*3600

export SPOT_PUBLISH_EPS="${SPOT_PUBLISH_EPS:-0.10}"
export FORCE_PUBLISH_INTERVAL_S="${FORCE_PUBLISH_INTERVAL_S:-2.0}"

export SLEEP_MIN_S="${SLEEP_MIN_S:-0.05}"
export SLEEP_MAX_S="${SLEEP_MAX_S:-1.0}"
export QUIET_DELTA="${QUIET_DELTA:-10}"
export HOT_DELTA="${HOT_DELTA:-100}"

# minimal | full
export SNAPSHOT_MODE="${SNAPSHOT_MODE:-minimal}"

# ------------------------------------------------
# Pub/Sub channels
# ------------------------------------------------
export USE_PUBSUB="${USE_PUBSUB:-1}"
export PUBSUB_PREFIX="${PUBSUB_PREFIX:-${SYMBOL}:chan}"
export FULL_CHANNEL="${FULL_CHANNEL:-${PUBSUB_PREFIX}:full}"
export DIFF_CHANNEL="${DIFF_CHANNEL:-${PUBSUB_PREFIX}:diff}"

# Per-expiry pubsub (off by default)
export USE_EXP_PUBSUB="${USE_EXP_PUBSUB:-0}"

# ------------------------------------------------
# VIX feed
# ------------------------------------------------
export VIX_SYMBOL="${VIX_SYMBOL:-I:VIX}"
export VIX_KEY_LATEST="${VIX_KEY_LATEST:-VIX:latest}"
export VIX_KEY_TRAIL="${VIX_KEY_TRAIL:-VIX:trail}"
export VIX_TRAIL_TTL="${VIX_TRAIL_TTL:-900}"
export VIX_CHANNEL="${VIX_CHANNEL:-VIX:chan:full}"

# ------------------------------------------------
# Diffs / aliases / HTTP
# ------------------------------------------------
export DIFF_FOR_ALL="${DIFF_FOR_ALL:-1}"          # 1 = diff for all expiries
export USE_DTE_ALIASES="${USE_DTE_ALIASES:-1}"    # SPX:DTE:<n>:* pointers

export REQUEST_TIMEOUT="${REQUEST_TIMEOUT:-12}"
export PAGE_LIMIT="${PAGE_LIMIT:-250}"
export INCLUDE_GREEKS="${INCLUDE_GREEKS:-1}"

# Spot freshness
export LIVE_MAX_AGE_S="${LIVE_MAX_AGE_S:-90}"
export DELAYED_MAX_AGE_S="${DELAYED_MAX_AGE_S:-1200}"

# Synthetic spot calc
export WINSOR_PCT="${WINSOR_PCT:-0.10}"

# Expiry tagging
export TAG_BACKFILL="${TAG_BACKFILL:-1}"

# ------------------------------------------------
# Debug / service identity
# ------------------------------------------------
export DEBUG_FEED_WORKER="${DEBUG_FEED_WORKER:-false}"

BREW_PY="/opt/homebrew/bin/python3.14"
BREW_REDIS="/opt/homebrew/bin/redis-cli"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE="feed_worker"
MAIN="$ROOT/services/massive/utils/dte_feed_worker.py"

VENV="$ROOT/.venv"
VENV_PY="$VENV/bin/python"

###############################################
# UI Helpers
###############################################
line() { echo "──────────────────────────────────────────────"; }

short_key() {
  local key="$1"
  if [[ -z "$key" ]]; then
    echo "(not set)"
  else
    local len=${#key}
    if (( len <= 8 )); then
      echo "len=$len (${key})"
    else
      echo "len=$len (${key:0:4}****${key: -4})"
    fi
  fi
}

check_tools() {
  for cmd in "$BREW_PY" "$VENV_PY" "$BREW_REDIS"; do
    if [[ -x "$cmd" ]]; then
      echo "Found $cmd"
    else
      echo "WARNING: Missing $cmd"
    fi
  done
}

show_config() {
  line
  echo " feed_worker configuration"
  line
  echo "ROOT:             $ROOT"
  echo "SERVICE_ID:       $SERVICE"
  echo "VENV_PY:          $VENV_PY"
  echo "MAIN:             $MAIN"
  echo ""
  echo "Redis:"
  echo "  SYSTEM_REDIS_URL = $SYSTEM_REDIS_URL"
  echo "  MARKET_REDIS_URL = $MARKET_REDIS_URL"
  echo "  INTEL_REDIS_URL  = $INTEL_REDIS_URL"
  echo "  REDIS_HOST       = $REDIS_HOST"
  echo "  REDIS_PORT       = $REDIS_PORT"
  echo "  REDIS_DB         = $REDIS_DB"
  echo ""
  echo "Polygon / Symbols:"
  echo "  POLYGON_API_KEY  = $(short_key "$POLYGON_API_KEY")"
  echo "  API_SYMBOL       = $API_SYMBOL"
  echo "  SYMBOL           = $SYMBOL"
  echo "  DTE_LIST         = $DTE_LIST"
  echo ""
  echo "Cadence / Snapshot:"
  echo "  TRAIL_TTL_SECONDS       = $TRAIL_TTL_SECONDS"
  echo "  SNAPSHOT_TTL_SECONDS    = $SNAPSHOT_TTL_SECONDS"
  echo "  SPOT_PUBLISH_EPS        = $SPOT_PUBLISH_EPS"
  echo "  FORCE_PUBLISH_INTERVAL  = $FORCE_PUBLISH_INTERVAL_S"
  echo "  SLEEP_MIN_S             = $SLEEP_MIN_S"
  echo "  SLEEP_MAX_S             = $SLEEP_MAX_S"
  echo "  QUIET_DELTA             = $QUIET_DELTA"
  echo "  HOT_DELTA               = $HOT_DELTA"
  echo "  SNAPSHOT_MODE           = $SNAPSHOT_MODE"
  echo ""
  echo "Pub/Sub:"
  echo "  USE_PUBSUB       = $USE_PUBSUB"
  echo "  PUBSUB_PREFIX    = $PUBSUB_PREFIX"
  echo "  FULL_CHANNEL     = $FULL_CHANNEL"
  echo "  DIFF_CHANNEL     = $DIFF_CHANNEL"
  echo "  USE_EXP_PUBSUB   = $USE_EXP_PUBSUB"
  echo ""
  echo "VIX:"
  echo "  VIX_SYMBOL       = $VIX_SYMBOL"
  echo "  VIX_KEY_LATEST   = $VIX_KEY_LATEST"
  echo "  VIX_KEY_TRAIL    = $VIX_KEY_TRAIL"
  echo "  VIX_TRAIL_TTL    = $VIX_TRAIL_TTL"
  echo "  VIX_CHANNEL      = $VIX_CHANNEL"
  echo ""
  echo "Diffs / Aliases / HTTP:"
  echo "  DIFF_FOR_ALL     = $DIFF_FOR_ALL"
  echo "  USE_DTE_ALIASES  = $USE_DTE_ALIASES"
  echo "  REQUEST_TIMEOUT  = $REQUEST_TIMEOUT"
  echo "  PAGE_LIMIT       = $PAGE_LIMIT"
  echo "  INCLUDE_GREEKS   = $INCLUDE_GREEKS"
  echo "  LIVE_MAX_AGE_S   = $LIVE_MAX_AGE_S"
  echo "  DELAYED_MAX_AGE_S= $DELAYED_MAX_AGE_S"
  echo "  WINSOR_PCT       = $WINSOR_PCT"
  echo "  TAG_BACKFILL     = $TAG_BACKFILL"
  echo ""
  echo "DEBUG_FEED_WORKER = $DEBUG_FEED_WORKER"
  line
}

run_foreground() {
  clear
  line
  echo " Launching $SERVICE (foreground)"
  line
  show_config
  echo ""
  check_tools
  echo ""
  echo "Running $SERVICE in foreground. Ctrl+C to stop."
  echo ""

  if [[ -z "${POLYGON_API_KEY}" ]]; then
    echo "ERROR: POLYGON_API_KEY is not set. Export a valid key and re-run."
    exit 1
  fi

  cd "$ROOT"
  export SERVICE_ID="$SERVICE"
  export DEBUG_FEED_WORKER

  # Exec in the foreground so stdout/stderr go directly to the terminal
  exec "$VENV_PY" "$MAIN" start
}

run_once() {
  clear
  line
  echo " Running $SERVICE once (single sweep)"
  line
  show_config
  echo ""
  check_tools
  echo ""

  if [[ -z "${POLYGON_API_KEY}" ]]; then
    echo "ERROR: POLYGON_API_KEY is not set. Export a valid key and re-run."
    exit 1
  fi

  cd "$ROOT"
  export SERVICE_ID="$SERVICE"
  export DEBUG_FEED_WORKER

  exec "$VENV_PY" "$MAIN" once
}

###############################################
# Menu
###############################################
menu() {
  while true; do
    clear
    line
    echo " MarketSwarm – feed_worker (DTE Feed Worker)"
    line
    echo ""
    echo "Current symbol:       $SYMBOL (API_SYMBOL=$API_SYMBOL)"
    echo "Current DTE_LIST:     $DTE_LIST"
    echo "Market Redis target:  $REDIS_HOST:$REDIS_PORT/$REDIS_DB"
    echo "SNAPSHOT_MODE:        $SNAPSHOT_MODE"
    echo "DEBUG_FEED_WORKER:    $DEBUG_FEED_WORKER"
    echo ""
    echo "Select Option:"
    echo ""
    echo "  1) Run feed_worker (foreground loop)"
    echo "  2) Run single sweep (once)"
    echo "  3) Toggle DEBUG_FEED_WORKER"
    echo "  4) Show full configuration"
    echo "  5) Quit"
    echo ""
    line
    read -rp "Enter choice [1-5]: " CH
    echo ""

    case "$CH" in
      1) run_foreground ;;  # exec, doesn't return
      2) run_once ;;        # exec, doesn't return
      3)
        if [[ "$DEBUG_FEED_WORKER" == "true" ]]; then
          DEBUG_FEED_WORKER="false"
        else
          DEBUG_FEED_WORKER="true"
        fi
        export DEBUG_FEED_WORKER
        echo "DEBUG_FEED_WORKER is now: $DEBUG_FEED_WORKER"
        sleep 1
        ;;
      4)
        show_config
        echo ""
        read -rp "Press ENTER to return to menu…" _
        ;;
      5) echo "Goodbye"; exit 0 ;;
      *) echo "Invalid choice"; sleep 1 ;;
    esac
  done
}

###############################################
# CLI override
###############################################
if [[ $# -gt 0 ]]; then
  case "$1" in
    run)   run_foreground ;;  # no menu, just run loop
    once)  run_once ;;        # one sweep, no menu
    *)
      echo "Usage: $0 [run|once]"
      exit 1
      ;;
  esac
else
  menu
fi