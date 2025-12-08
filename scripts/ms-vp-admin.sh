#!/opt/homebrew/bin/bash
set -euo pipefail

###############################################
# MarketSwarm – VP Admin (Volume Profile)
# One-off backfill + model builder
###############################################

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT/.venv"
VENV_PY="$VENV/bin/python"

BREW_PY="/opt/homebrew/bin/python3.14"

DL_SCRIPT="$ROOT/services/massive/intel/admin/vp_download_history.py"
BUILD_SCRIPT="$ROOT/services/massive/intel/admin/vp_build_profile.py"

###############################################
# Environment
###############################################
export SYSTEM_REDIS_URL="${SYSTEM_REDIS_URL:-redis://127.0.0.1:6379}"
export MARKET_REDIS_URL="${MARKET_REDIS_URL:-redis://127.0.0.1:6380}"
export POLYGON_API_KEY="${POLYGON_API_KEY:-YOUR_KEY_HERE}"

# Default config
VP_TICKER="${VP_TICKER:-SPY}"     # underlying ETF to download
VP_YEARS="${VP_YEARS:-5}"         # years of history
VP_PUBLISH_MODE="${VP_PUBLISH_MODE:-raw}"  # raw|tv|both|none
VP_DATA_DIR="${VP_DATA_DIR:-$ROOT/data/vp}"

###############################################
# Helpers
###############################################
line() { echo "──────────────────────────────────────────────"; }

check_tools() {
  for cmd in "$BREW_PY" "$VENV_PY"; do
    if [[ -x "$cmd" ]]; then
      echo "Found $cmd"
    else
      echo "WARNING: Missing $cmd"
    fi
  done

  if [[ ! -f "$DL_SCRIPT" ]]; then
    echo "WARNING: Downloader script not found at $DL_SCRIPT"
  fi
  if [[ ! -f "$BUILD_SCRIPT" ]]; then
    echo "WARNING: Builder script not found at $BUILD_SCRIPT"
  fi
}

ensure_data_dir() {
  mkdir -p "$VP_DATA_DIR"
}

run_download() {
  clear
  line
  echo " VP Admin – Download Minute History"
  line
  echo "ROOT:        $ROOT"
  echo "VENV_PY:     $VENV_PY"
  echo "DL_SCRIPT:   $DL_SCRIPT"
  echo "POLYGON_API: $POLYGON_API_KEY"
  echo ""
  echo "Current defaults:"
  echo "  Ticker: $VP_TICKER"
  echo "  Years:  $VP_YEARS"
  echo "  Data dir: $VP_DATA_DIR"
  echo ""
  read -rp "Enter ticker [${VP_TICKER}]: " TICK
  read -rp "Enter years (N|max) [${VP_YEARS}]: " YRS

  TICK="${TICK:-$VP_TICKER}"
  YRS="${YRS:-$VP_YEARS}"

  ensure_data_dir

  echo ""
  line
  echo "Downloading $YRS years of 1-min bars for $TICK ..."
  line
  echo ""

  cd "$ROOT"
  exec "$VENV_PY" "$DL_SCRIPT" \
    --ticker "$TICK" \
    --years "$YRS" \
    --out-dir "$VP_DATA_DIR"
}

run_build() {
  clear
  line
  echo " VP Admin – Build Volume Profile Model"
  line
  echo "ROOT:        $ROOT"
  echo "VENV_PY:     $VENV_PY"
  echo "BUILD_SCRIPT:$BUILD_SCRIPT"
  echo ""
  echo "Current defaults:"
  echo "  Ticker:        $VP_TICKER"
  echo "  Data dir:      $VP_DATA_DIR"
  echo "  Publish mode:  $VP_PUBLISH_MODE"
  echo ""
  echo "Available files in $VP_DATA_DIR:"
  ls -1 "$VP_DATA_DIR" 2>/dev/null || echo "  (none)"
  echo ""
  read -rp "Enter ticker [${VP_TICKER}]: " TICK
  read -rp "Enter JSON file name (relative to $VP_DATA_DIR): " FILE
  read -rp "Publish mode raw|tv|both|none [${VP_PUBLISH_MODE}]: " PMODE

  TICK="${TICK:-$VP_TICKER}"
  PMODE="${PMODE:-$VP_PUBLISH_MODE}"

  if [[ -z "$FILE" ]]; then
    echo "No file specified. Aborting."
    sleep 1
    return
  fi

  FULL_PATH="$VP_DATA_DIR/$FILE"
  if [[ ! -f "$FULL_PATH" ]]; then
    echo "File not found: $FULL_PATH"
    sleep 2
    return
  fi

  echo ""
  line
  echo "Building volume profile for $TICK from:"
  echo "  $FULL_PATH"
  echo "Publish mode: $PMODE"
  line
  echo ""

  cd "$ROOT"
  exec "$VENV_PY" "$BUILD_SCRIPT" \
    --ticker "$TICK" \
    --file "$FULL_PATH" \
    --publish "$PMODE"
}

menu() {
  while true; do
    clear
    line
    echo " MarketSwarm – VP Admin (Volume Profile)"
    line
    echo ""
    echo "Current configuration:"
    echo "  POLYGON_API_KEY (set?):     ${POLYGON_API_KEY:+yes}"
    echo "  SYSTEM_REDIS_URL:           $SYSTEM_REDIS_URL"
    echo "  MARKET_REDIS_URL:           $MARKET_REDIS_URL"
    echo "  VP_TICKER:                  $VP_TICKER"
    echo "  VP_YEARS:                   $VP_YEARS"
    echo "  VP_PUBLISH_MODE:            $VP_PUBLISH_MODE"
    echo "  VP_DATA_DIR:                $VP_DATA_DIR"
    echo ""
    echo "Select Option:"
    echo ""
    echo "  1) Download 1-min history (Polygon → JSON file)"
    echo "  2) Build volume profile model (JSON file → Redis)"
    echo "  3) Quit"
    echo ""
    line
    read -rp "Enter choice [1-3]: " CH
    echo ""

    case "$CH" in
      1) run_download ;;  # exec, doesn't return
      2) run_build ;;     # exec, doesn't return
      3)
        echo "Goodbye"
        exit 0
        ;;
      *)
        echo "Invalid choice"
        sleep 1
        ;;
    esac
  done
}

###############################################
# Entry
###############################################
if [[ $# -gt 0 ]]; then
  case "$1" in
    download) run_download ;;
    build)    run_build ;;
    *)
      echo "Usage: $0 [download|build]"
      exit 1
      ;;
  esac
else
  check_tools
  sleep 1
  menu
fi