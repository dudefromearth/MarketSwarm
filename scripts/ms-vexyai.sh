#!/opt/homebrew/bin/bash
set -euo pipefail

###############################################
# MarketSwarm Vexy AI – Menu Launcher
# (Modeled exactly on ms-rssagg.sh — first principles)
###############################################

# Environment (safe)
export XAI_API_KEY="YOUR_XAI_KEY_HERE"
export OPENAI_API_KEY="sk-..."  # fallback if needed

export SYSTEM_REDIS_URL="redis://127.0.0.1:6379"
export MARKET_REDIS_URL="redis://127.0.0.1:6380"
export INTEL_REDIS_URL="redis://127.0.0.1:6381"

# Vexy modes
export VEXY_MODE="${VEXY_MODE:-full}"                    # full | epochs_only | events_only | silent
export FORCE_EPOCH="${FORCE_EPOCH:-false}"               # force next epoch to speak
export DEBUG_VEXY="${DEBUG_VEXY:-false}"                 # verbose logging

BREW_PY="/opt/homebrew/bin/python3.14"
BREW_REDIS="/opt/homebrew/bin/redis-cli"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE="vexy_ai"
MAIN="$ROOT/services/vexy_ai/main.py"

VENV="$ROOT/.venv"
VENV_PY="$VENV/bin/python"

###############################################
# UI Helpers
###############################################
line() { echo "──────────────────────────────────────────────"; }

show_last_commentary() {
  clear
  line
  echo " Latest Vexy Commentary"
  line
  echo ""

  # Epoch commentary (stored at vexy:model:playbyplay:epoch:latest)
  echo "📅 EPOCH COMMENTARY:"
  EPOCH_RAW=$($BREW_REDIS -h 127.0.0.1 -p 6380 GET "vexy:model:playbyplay:epoch:latest" 2>/dev/null)
  if [[ -n "$EPOCH_RAW" && "$EPOCH_RAW" != "nil" ]]; then
    echo "$EPOCH_RAW" | jq -r '"  [\(.ts)] \(.meta.epoch)\n  \(.text)"' 2>/dev/null || echo "  (parse error)"
  else
    echo "  (none)"
  fi

  echo ""

  # Event commentary (stored at vexy:model:playbyplay:event:latest)
  echo "💥 EVENT COMMENTARY:"
  EVENT_RAW=$($BREW_REDIS -h 127.0.0.1 -p 6380 GET "vexy:model:playbyplay:event:latest" 2>/dev/null)
  if [[ -n "$EVENT_RAW" && "$EVENT_RAW" != "nil" ]]; then
    echo "$EVENT_RAW" | jq -r '"  [\(.ts)] \(.meta.type // "event")\n  \(.text)"' 2>/dev/null || echo "  (parse error)"
  else
    echo "  (none)"
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
  echo " MarketSwarm – Vexy AI Play-by-Play Engine"
  line
  echo "Select Mode:"
  echo ""
  echo "  1) FULL (epochs + events)"
  echo "  2) Epochs Only"
  echo "  3) Events Only"
  echo "  4) Silent (run but don’t speak)"
  echo "  5) View Last Commentary"
  echo "  6) Quit"
  echo ""
  echo "  9) FORCE Next Epoch (debug)"
  line
  read -rp "Enter choice [1-9]: " CH
  echo ""

  case "$CH" in
    1) export VEXY_MODE="full" ;;
    2) export VEXY_MODE="epochs_only" ;;
    3) export VEXY_MODE="events_only" ;;
    4) export VEXY_MODE="silent" ;;
    5) show_last_commentary; menu ;;
    6) echo "Goodbye"; exit 0 ;;
    9) export FORCE_EPOCH="true"; echo "Next epoch will speak regardless of time" ;;
    *) echo "Invalid"; sleep 1; menu ;;
  esac
}

###############################################
# Argument override (same as rss_agg)
###############################################
if [[ $# -gt 0 ]]; then
  case "$1" in
    full)           export VEXY_MODE="full" ;;
    epochs_only)    export VEXY_MODE="epochs_only" ;;
    events_only)    export VEXY_MODE="events_only" ;;
    silent)         export VEXY_MODE="silent" ;;
    force_epoch)    export FORCE_EPOCH="true" ;;
    debug)          export DEBUG_VEXY="true" ;;
    show)           show_last_commentary; exit 0 ;;
    *)              echo "Usage: $0 [full|epochs_only|events_only|silent|force_epoch|show]"; exit 1 ;;
  esac
else
  menu
fi

###############################################
# Bootstrap & Validation
###############################################
line
echo " Vexy AI Service Runner (Brew)"
line
echo "ROOT: $ROOT"
echo "MODE: $VEXY_MODE"
[[ "$FORCE_EPOCH" == "true" ]] && echo "FORCE_EPOCH: enabled"
[[ "$DEBUG_VEXY" == "true" ]] && echo "DEBUG: enabled"
echo ""

# Validate tools
for cmd in "$BREW_PY" "$VENV_PY" "$BREW_REDIS"; do
  [[ -x "$cmd" ]] && echo "Found $cmd" || { echo "Missing $cmd"; exit 1; }
done

# Validate truth
HAS_TRUTH=$($BREW_REDIS -h 127.0.0.1 -p 6379 EXISTS truth)
[[ "$HAS_TRUTH" -eq 1 ]] && echo "Truth found" || { echo "Missing truth"; exit 1; }

###############################################
# Launch Vexy
###############################################
line
echo "Launching Vexy AI (MODE=$VEXY_MODE)"
line

export SERVICE_ID="$SERVICE"
exec "$VENV_PY" "$MAIN"