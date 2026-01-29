#!/opt/homebrew/bin/bash
set -euo pipefail

###############################################
# MarketSwarm – massive (Massive Market Model)
# Foreground dev runner with interactive menu
###############################################

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE="massive"

MAIN_DIRECT="$ROOT/services/massive/main.py"
MAIN_SUPERVISED="$ROOT/services/massive/supervised_main.py"

VENV="$ROOT/.venv"
VENV_PY="$VENV/bin/python"

# Capture locations (must match truth.json)
CAPTURE_ROOT="$ROOT/ws_captures"
CHAIN_DIR="$CAPTURE_ROOT/chain"

###############################################
# Defaults
###############################################
RUN_MODE="direct"   # direct | supervised

###############################################
# Helpers
###############################################
set_primary_mode() {
  : "${MASSIVE_WS_ENABLED:=true}"
  export MASSIVE_WS_CAPTURE="false"
  export MASSIVE_WS_REPLAY="false"
  unset MASSIVE_REPLAY_SESSION
}

set_capture_mode() {
  export MASSIVE_WS_ENABLED="true"
  export MASSIVE_WS_CAPTURE="true"
  export MASSIVE_WS_REPLAY="false"
  unset MASSIVE_REPLAY_SESSION
}

set_replay_mode() {
  export MASSIVE_WS_ENABLED="false"
  export MASSIVE_WS_CAPTURE="false"
  export MASSIVE_WS_REPLAY="true"
}

toggle_ws() {
  if [[ "${MASSIVE_WS_ENABLED:-false}" == "true" ]]; then
    export MASSIVE_WS_ENABLED="false"
  else
    export MASSIVE_WS_ENABLED="true"
  fi
}

set_debug_on() {
  export DEBUG_MASSIVE="true"
}

set_debug_off() {
  export DEBUG_MASSIVE="false"
}

toggle_debug() {
  if [[ "${DEBUG_MASSIVE:-false}" == "true" ]]; then
    set_debug_off
  else
    set_debug_on
  fi
}

toggle_run_mode() {
  if [[ "$RUN_MODE" == "direct" ]]; then
    RUN_MODE="supervised"
  else
    RUN_MODE="direct"
  fi
}

show_mode() {
  echo "Resolved mode:"
  echo "  RUN_MODE   : ${RUN_MODE}"
  echo "  WS_ENABLED : ${MASSIVE_WS_ENABLED} $( [[ "${MASSIVE_WS_ENABLED}" == "true" ]] && echo "🟢" || echo "🔴" )"
  echo "  WS_CAPTURE : ${MASSIVE_WS_CAPTURE}"
  echo "  WS_REPLAY  : ${MASSIVE_WS_REPLAY}"
  echo "  DEBUG      : ${DEBUG_MASSIVE:-false}"
  if [[ "${MASSIVE_WS_REPLAY}" == "true" ]]; then
    echo "  REPLAY_SESSION : ${MASSIVE_REPLAY_SESSION:-<not selected>}"
  fi
}

###############################################
# Replay session discovery
###############################################
select_replay_session() {
  if [[ ! -d "$CHAIN_DIR" ]]; then
    echo "Replay capture directory not found:"
    echo "  $CHAIN_DIR"
    sleep 2
    return 1
  fi

  mapfile -t SESSIONS < <(
    ls "$CHAIN_DIR"/chain_*.jsonl 2>/dev/null \
      | sed -E 's/.*chain_([0-9]{8}_[0-9]{6})\.jsonl/\1/' \
      | sort -r
  )

  if [[ ${#SESSIONS[@]} -eq 0 ]]; then
    echo "No replay sessions found."
    sleep 2
    return 1
  fi

  echo ""
  echo "Available Replay Sessions:"
  echo "──────────────────────────"
  for i in "${!SESSIONS[@]}"; do
    printf "  %2d) %s\n" "$((i+1))" "${SESSIONS[$i]}"
  done
  echo ""

  read -rp "Select replay session [1-${#SESSIONS[@]}]: " idx

  if ! [[ "$idx" =~ ^[0-9]+$ ]] || (( idx < 1 || idx > ${#SESSIONS[@]} )); then
    echo "Invalid selection"
    sleep 1
    return 1
  fi

  export MASSIVE_REPLAY_SESSION="${SESSIONS[$((idx-1))]}"
  echo "Selected replay session: $MASSIVE_REPLAY_SESSION"
  sleep 1
}

###############################################
# Interactive Menu
###############################################
menu() {
  set_primary_mode
  set_debug_off
  RUN_MODE="direct"

  while true; do
    clear
    echo "──────────────────────────────────────────────"
    echo " MarketSwarm – massive (Mode Selector)"
    echo "──────────────────────────────────────────────"
    echo ""
    show_mode
    echo ""
    echo "Modes:"
    echo "  1) Primary (live)"
    echo "  2) Capture (live + record)"
    echo "  3) Replay (disk → redis)"
    echo ""
    echo "Run Control:"
    echo "  s) Toggle Supervisor (direct ↔ supervised)"
    echo "  w) Toggle WebSocket (on ↔ off)"
    echo ""
    echo "Debug:"
    echo "  d) Toggle DEBUG_MASSIVE"
    echo ""
    echo "Actions:"
    echo "  r) Run Massive"
    echo "  q) Quit"
    echo ""
    echo "──────────────────────────────────────────────"
    read -rp "Choose [1,2,3,s,w,d,r,q]: " choice
    echo ""

    case "$choice" in
      1)
        set_primary_mode
        ;;
      2)
        set_capture_mode
        ;;
      3)
        if select_replay_session; then
          set_replay_mode
        fi
        ;;
      s|S)
        toggle_run_mode
        ;;
      w|W)
        toggle_ws
        ;;
      d|D)
        toggle_debug
        ;;
      r|R)
        run_foreground
        ;;
      q|Q)
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
# Run foreground
###############################################
run_foreground() {
  clear
  echo "Launching Massive with mode:"
  show_mode
  echo "──────────────────────────────────────────────"
  echo ""

  cd "$ROOT"
  export SERVICE_ID="$SERVICE"

  if [[ "$RUN_MODE" == "supervised" ]]; then
    exec "$VENV_PY" "$MAIN_SUPERVISED"
  else
    exec "$VENV_PY" "$MAIN_DIRECT"
  fi
}

# If no args, show menu; if "run", go straight
if [[ $# -gt 0 && "$1" == "run" ]]; then
  set_primary_mode
  set_debug_off
  RUN_MODE="direct"
  run_foreground
else
  menu
fi