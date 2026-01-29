#!/opt/homebrew/bin/bash
set -euo pipefail

###############################################
# MarketSwarm – SSE Gateway
# Foreground-only service control
###############################################

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE_DIR="$ROOT/services/sse"

###############################################
# Configuration
###############################################
export TRUTH_REDIS_URL="redis://127.0.0.1:6379"
export TRUTH_REDIS_KEY="truth"
export SSE_PORT="${SSE_PORT:-3001}"
export SSE_POLL_INTERVAL_MS="${SSE_POLL_INTERVAL_MS:-2000}"

###############################################
# Colors
###############################################
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${BLUE}[INFO]${NC} $1"; }
log_ok()    { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

###############################################
# Functions
###############################################

check_deps() {
  if ! command -v node &>/dev/null; then
    log_error "node not found. Please install Node.js 18+"
    exit 1
  fi

  local node_version
  node_version=$(node -v | sed 's/v//' | cut -d. -f1)
  if [[ "$node_version" -lt 18 ]]; then
    log_error "Node.js 18+ required (found v$node_version)"
    exit 1
  fi
}

install_deps() {
  log_info "Installing dependencies..."
  cd "$SERVICE_DIR"
  npm install
  log_ok "Dependencies installed."
}

get_pids_on_port() {
  lsof -ti:"$SSE_PORT" 2>/dev/null || echo ""
}

is_port_in_use() {
  [[ -n "$(get_pids_on_port)" ]]
}

kill_port() {
  local pids
  pids=$(get_pids_on_port)

  if [[ -z "$pids" ]]; then
    return 0
  fi

  log_info "Killing process(es) on port $SSE_PORT: $pids"

  for pid in $pids; do
    kill "$pid" 2>/dev/null || true
  done
  sleep 1

  pids=$(get_pids_on_port)
  if [[ -n "$pids" ]]; then
    for pid in $pids; do
      kill -9 "$pid" 2>/dev/null || true
    done
    sleep 0.5
  fi

  if is_port_in_use; then
    log_error "Failed to free port $SSE_PORT"
    return 1
  fi

  log_ok "Port $SSE_PORT is now free"
}

status_service() {
  echo
  echo "═══════════════════════════════════════════════════════"
  echo " SSE Gateway Status"
  echo "═══════════════════════════════════════════════════════"

  local pids
  pids=$(get_pids_on_port)

  if [[ -n "$pids" ]]; then
    echo -e "Status: ${GREEN}RUNNING${NC} (PID: $pids)"
    echo "Port: $SSE_PORT"
    echo
    log_info "Health check:"
    curl -sf "http://localhost:${SSE_PORT}/api/health" 2>/dev/null && echo || log_warn "Not responding"
  else
    echo -e "Status: ${RED}STOPPED${NC}"
    echo "Port $SSE_PORT is free"
  fi
  echo
}

run_service() {
  if is_port_in_use; then
    log_warn "Port $SSE_PORT is in use, cleaning up..."
    kill_port || exit 1
  fi

  check_deps

  if [[ ! -d "$SERVICE_DIR/node_modules" ]]; then
    install_deps
  fi

  echo
  echo "═══════════════════════════════════════════════════════"
  echo " MarketSwarm – SSE Gateway"
  echo "═══════════════════════════════════════════════════════"
  echo " Port:     $SSE_PORT"
  echo " Poll:     ${SSE_POLL_INTERVAL_MS}ms"
  echo " Redis:    $TRUTH_REDIS_URL"
  echo "═══════════════════════════════════════════════════════"
  echo
  log_info "Starting... (Ctrl+C to stop)"
  echo

  cd "$SERVICE_DIR"
  exec node src/index.js
}

show_menu() {
  echo
  echo "═══════════════════════════════════════════════════════"
  echo " MarketSwarm – SSE Gateway"
  echo "═══════════════════════════════════════════════════════"

  local pids
  pids=$(get_pids_on_port)
  if [[ -n "$pids" ]]; then
    echo -e " Status: ${GREEN}● RUNNING${NC} (PID: $pids)"
  else
    echo -e " Status: ${RED}● STOPPED${NC}"
  fi

  echo
  echo "  1) Run (foreground)"
  echo "  2) Stop"
  echo "  3) Status"
  echo "  4) Install dependencies"
  echo "  q) Quit"
  echo
  echo -n "Choice: "
}

###############################################
# Main
###############################################

case "${1:-}" in
  run|start|fg|foreground)
    run_service
    ;;
  stop|kill)
    if is_port_in_use; then
      kill_port
    else
      log_info "SSE Gateway is not running"
    fi
    ;;
  status)
    status_service
    ;;
  install)
    install_deps
    ;;
  help|-h|--help)
    echo "Usage: $(basename "$0") [command]"
    echo
    echo "Commands:"
    echo "  run      Run SSE Gateway (foreground)"
    echo "  stop     Stop SSE Gateway"
    echo "  status   Show status"
    echo "  install  Install npm dependencies"
    echo
    echo "Without arguments, shows interactive menu."
    ;;
  "")
    while true; do
      show_menu
      read -r choice
      case "$choice" in
        1) run_service ;;
        2) if is_port_in_use; then kill_port; else log_info "Not running"; fi ;;
        3) status_service ;;
        4) install_deps ;;
        q|Q) exit 0 ;;
        *) log_error "Invalid choice" ;;
      esac
    done
    ;;
  *)
    log_error "Unknown command: $1"
    echo "Run '$(basename "$0") help' for usage"
    exit 1
    ;;
esac
