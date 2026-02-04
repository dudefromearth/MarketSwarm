#!/opt/homebrew/bin/bash
set -euo pipefail

###############################################
# MarketSwarm – Service Manager (Shell Front-End)
#
# Wrapper for the Python service manager.
# Provides both CLI pass-through and interactive menu.
###############################################

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PY="$ROOT/.venv/bin/python"
MANAGER="$ROOT/scripts/service_manager.py"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

line() { echo "──────────────────────────────────────────────"; }

###############################################
# Validation
###############################################
if [[ ! -x "$VENV_PY" ]]; then
  echo -e "${RED}[ERROR]${NC} Python venv not found: $VENV_PY"
  exit 1
fi

if [[ ! -f "$MANAGER" ]]; then
  echo -e "${RED}[ERROR]${NC} Service manager not found: $MANAGER"
  exit 1
fi

###############################################
# Run Python manager (CLI mode)
###############################################
run_manager() {
  "$VENV_PY" "$MANAGER" "$@"
}

###############################################
# Interactive Menu
###############################################
menu() {
  while true; do
    clear
    line
    echo " MarketSwarm – Service Manager"
    line
    echo ""

    # Show quick status
    run_manager status 2>/dev/null || true

    echo ""
    echo "Actions:"
    echo "  1) Start All Services"
    echo "  2) Stop All Services"
    echo "  3) Restart All Services"
    echo ""
    echo "Individual:"
    echo "  4) Start Service..."
    echo "  5) Stop Service..."
    echo "  6) View Logs..."
    echo ""
    echo "  r) Refresh Status"
    echo "  q) Quit"
    echo ""
    line
    read -rp "Choose: " choice

    case "$choice" in
      1)
        echo ""
        run_manager start
        echo ""
        read -n 1 -s -r -p "Press any key to continue..."
        ;;
      2)
        echo ""
        run_manager stop
        echo ""
        read -n 1 -s -r -p "Press any key to continue..."
        ;;
      3)
        echo ""
        run_manager restart
        echo ""
        read -n 1 -s -r -p "Press any key to continue..."
        ;;
      4)
        select_service "start"
        ;;
      5)
        select_service "stop"
        ;;
      6)
        select_service "logs"
        ;;
      r|R)
        # Just refresh - loop will redraw
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

select_service() {
  local action="$1"
  echo ""
  echo "Available services:"
  echo ""

  # Get service list
  local services=(massive rss_agg vexy_ai sse journal content_anal copilot)

  local i=1
  for svc in "${services[@]}"; do
    printf "  %d) %s\n" "$i" "$svc"
    ((i++))
  done
  echo "  q) Cancel"
  echo ""
  read -rp "Select service [1-${#services[@]}]: " sel

  if [[ "$sel" == "q" || "$sel" == "Q" ]]; then
    return
  fi

  if ! [[ "$sel" =~ ^[0-9]+$ ]] || (( sel < 1 || sel > ${#services[@]} )); then
    echo "Invalid selection"
    sleep 1
    return
  fi

  local service="${services[$((sel-1))]}"
  echo ""

  case "$action" in
    start)
      run_manager start "$service"
      ;;
    stop)
      run_manager stop "$service"
      ;;
    logs)
      echo "Showing last 50 lines of $service logs (Ctrl+C to exit)..."
      echo ""
      run_manager logs "$service" -n 50
      ;;
  esac

  echo ""
  read -n 1 -s -r -p "Press any key to continue..."
}

###############################################
# Main
###############################################
if [[ $# -gt 0 ]]; then
  # CLI mode - pass through to Python manager
  run_manager "$@"
else
  # Interactive menu
  menu
fi
