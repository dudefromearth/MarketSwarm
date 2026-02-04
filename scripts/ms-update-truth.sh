#!/opt/homebrew/bin/bash
set -euo pipefail

###############################################
# MarketSwarm – Update Truth (Consolidated)
#
# Combines truth building and Redis loading:
# 1. Build truth.json from component JSONs
# 2. Clear Redis buses
# 3. Load truth.json into Redis
#
# Supports both CLI and menu-driven interfaces.
###############################################

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ------------------------------------------------
# Path resolution
# ------------------------------------------------
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPTS_DIR="$ROOT/scripts"
TRUTH_FILE="$SCRIPTS_DIR/truth.json"
BUILD_SCRIPT="$SCRIPTS_DIR/build_truth.py"

VENV="$ROOT/.venv"
VENV_PY="$VENV/bin/python"

# Track if we're in menu mode (for pausing)
MENU_MODE=false

###############################################
# UI Helpers
###############################################
line() { echo "──────────────────────────────────────────────"; }

info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; }

pause() {
  if $MENU_MODE; then
    echo ""
    read -n 1 -s -r -p "Press any key to continue..."
  fi
}

die() {
  error "$1"
  echo ""
  error "Truth update FAILED. Resolve the error before restarting services."
  pause
  exit 1
}

###############################################
# Preconditions
###############################################
check_preconditions() {
  # Check Python venv
  [[ -x "$VENV_PY" ]] || { error "venv python not found at $VENV_PY"; return 1; }

  # Check build script
  [[ -f "$BUILD_SCRIPT" ]] || { error "build_truth.py not found at $BUILD_SCRIPT"; return 1; }

  # Check jq
  command -v jq >/dev/null 2>&1 || { error "jq is required but not installed"; return 1; }

  # Check redis-cli
  command -v redis-cli >/dev/null 2>&1 || { error "redis-cli not found in PATH"; return 1; }

  return 0
}

###############################################
# Redis Helpers
###############################################
get_redis_buses() {
  [[ -f "$TRUTH_FILE" ]] || return 1
  jq -r '
    .buses
    | to_entries[]
    | select(.value.url | startswith("redis://"))
    | .key + "|" + .value.role + "|" +
      (.value.url | sub("^redis://"; "") )
  ' "$TRUTH_FILE"
}

redis_ping() {
  local host="$1" port="$2"
  redis-cli -h "$host" -p "$port" PING 2>/dev/null
}

show_redis_status() {
  if [[ ! -f "$TRUTH_FILE" ]]; then
    echo "  (no truth.json found)"
    return
  fi

  readarray -t buses < <(get_redis_buses)

  for entry in "${buses[@]}"; do
    IFS='|' read -r key role endpoint <<< "$entry"
    host="${endpoint%%:*}"
    port="${endpoint##*:}"

    local status
    if [[ "$(redis_ping "$host" "$port")" == "PONG" ]]; then
      status="${GREEN}RUNNING${NC}"
    else
      status="${RED}NOT RUNNING${NC}"
    fi

    printf "  %-14s %-8s %s:%s  [%b]\n" "$key" "$role" "$host" "$port" "$status"
  done
}

###############################################
# Step 1: Build Truth
###############################################
do_build_truth() {
  clear
  line
  echo " Step 1: Build Truth"
  line
  echo ""

  info "Checking preconditions..."
  if ! check_preconditions; then
    pause
    return 1
  fi
  success "Preconditions OK"
  echo ""

  info "Running build_truth.py..."
  echo ""

  # Run the build script
  if ! "$VENV_PY" "$BUILD_SCRIPT"; then
    error "build_truth.py failed"
    pause
    return 1
  fi

  # Verify the output exists and is valid JSON
  if [[ ! -f "$TRUTH_FILE" ]]; then
    error "truth.json was not created"
    pause
    return 1
  fi

  if ! jq empty "$TRUTH_FILE" 2>/dev/null; then
    error "truth.json is not valid JSON"
    pause
    return 1
  fi

  echo ""
  success "truth.json built successfully"
  echo ""
  info "Truth summary:"
  jq '{version, description, buses: (.buses | keys | length), components: (.components | keys | length)}' "$TRUTH_FILE"

  pause
  return 0
}

###############################################
# Step 2: Clear Redis Buses
###############################################
do_clear_redis() {
  clear
  line
  echo " Step 2: Clear Redis Buses"
  line
  echo ""

  if [[ ! -f "$TRUTH_FILE" ]]; then
    error "truth.json not found. Run Build first."
    pause
    return 1
  fi

  info "Current Redis status:"
  echo ""
  show_redis_status
  echo ""

  if $MENU_MODE; then
    warn "This will FLUSHALL on each reachable Redis bus."
    echo ""
    read -rp "Type CLEAR to confirm: " confirm
    if [[ "$confirm" != "CLEAR" ]]; then
      echo "Aborted."
      pause
      return 1
    fi
    echo ""
  fi

  readarray -t buses < <(get_redis_buses)

  if [[ ${#buses[@]} -eq 0 ]]; then
    error "No Redis buses found in truth.json"
    pause
    return 1
  fi

  local cleared=0
  local failed=0

  for entry in "${buses[@]}"; do
    IFS='|' read -r key role endpoint <<< "$entry"
    host="${endpoint%%:*}"
    port="${endpoint##*:}"

    printf "  %-14s %s:%s ... " "$key" "$host" "$port"

    if [[ "$(redis_ping "$host" "$port")" == "PONG" ]]; then
      if redis-cli -h "$host" -p "$port" FLUSHALL >/dev/null 2>&1; then
        echo -e "${GREEN}cleared${NC}"
        ((cleared++))
      else
        echo -e "${RED}FLUSHALL failed${NC}"
        ((failed++))
      fi
    else
      echo -e "${YELLOW}not reachable (skipped)${NC}"
    fi
  done

  echo ""

  if [[ $failed -gt 0 ]]; then
    error "Failed to clear $failed Redis bus(es)"
    pause
    return 1
  fi

  if [[ $cleared -eq 0 ]]; then
    error "No Redis buses were cleared (none reachable)"
    pause
    return 1
  fi

  success "Cleared $cleared Redis bus(es)"
  pause
  return 0
}

###############################################
# Step 3: Load Truth into Redis
###############################################
do_load_truth() {
  clear
  line
  echo " Step 3: Load Truth into Redis"
  line
  echo ""

  if [[ ! -f "$TRUTH_FILE" ]]; then
    error "truth.json not found. Run Build first."
    pause
    return 1
  fi

  readarray -t buses < <(get_redis_buses)

  # Find system-redis endpoint
  local system_entry
  system_entry="$(printf "%s\n" "${buses[@]}" | grep "^system-redis|" || true)"

  if [[ -z "$system_entry" ]]; then
    error "system-redis bus not found in truth.json"
    pause
    return 1
  fi

  IFS='|' read -r _ _ endpoint <<< "$system_entry"
  local sys_host="${endpoint%%:*}"
  local sys_port="${endpoint##*:}"

  info "Loading truth into system-redis ($sys_host:$sys_port)..."

  if [[ "$(redis_ping "$sys_host" "$sys_port")" != "PONG" ]]; then
    error "system-redis is not reachable"
    pause
    return 1
  fi

  if ! redis-cli -h "$sys_host" -p "$sys_port" SET truth "$(cat "$TRUTH_FILE")" >/dev/null; then
    error "Failed to SET truth in system-redis"
    pause
    return 1
  fi

  # Verify
  if ! redis-cli -h "$sys_host" -p "$sys_port" EXISTS truth | grep -q '^1$'; then
    error "Verification failed - truth key not present"
    pause
    return 1
  fi

  echo ""
  success "Truth loaded and verified in system-redis"
  pause
  return 0
}

###############################################
# Full Update (All Steps)
###############################################
do_full_update() {
  clear
  line
  echo " Full Update: Build → Clear → Load"
  line
  echo ""

  info "This will:"
  echo "  1. Build truth.json from component JSONs"
  echo "  2. Clear all Redis buses (FLUSHALL)"
  echo "  3. Load truth.json into system-redis"
  echo ""

  if $MENU_MODE; then
    read -rp "Continue? [y/N] " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
      echo "Aborted."
      pause
      return 1
    fi
    echo ""
  fi

  # Step 1: Build
  info "Step 1/3: Building truth.json..."
  echo ""
  if ! "$VENV_PY" "$BUILD_SCRIPT"; then
    error "Build failed"
    pause
    return 1
  fi

  if [[ ! -f "$TRUTH_FILE" ]] || ! jq empty "$TRUTH_FILE" 2>/dev/null; then
    error "truth.json is missing or invalid"
    pause
    return 1
  fi
  success "Build complete"
  echo ""

  # Step 2: Clear Redis
  info "Step 2/3: Clearing Redis buses..."
  echo ""

  readarray -t buses < <(get_redis_buses)
  local cleared=0

  for entry in "${buses[@]}"; do
    IFS='|' read -r key role endpoint <<< "$entry"
    host="${endpoint%%:*}"
    port="${endpoint##*:}"

    printf "  %-14s ... " "$key"
    if [[ "$(redis_ping "$host" "$port")" == "PONG" ]]; then
      redis-cli -h "$host" -p "$port" FLUSHALL >/dev/null 2>&1
      echo -e "${GREEN}cleared${NC}"
      ((cleared++))
    else
      echo -e "${YELLOW}skipped${NC}"
    fi
  done

  if [[ $cleared -eq 0 ]]; then
    error "No Redis buses cleared"
    pause
    return 1
  fi
  echo ""
  success "Cleared $cleared bus(es)"
  echo ""

  # Step 3: Load Truth
  info "Step 3/3: Loading truth into system-redis..."

  local system_entry
  system_entry="$(printf "%s\n" "${buses[@]}" | grep "^system-redis|" || true)"
  IFS='|' read -r _ _ endpoint <<< "$system_entry"
  local sys_host="${endpoint%%:*}"
  local sys_port="${endpoint##*:}"

  if ! redis-cli -h "$sys_host" -p "$sys_port" SET truth "$(cat "$TRUTH_FILE")" >/dev/null; then
    error "Failed to load truth"
    pause
    return 1
  fi

  success "Truth loaded"
  echo ""

  line
  success "Full update complete! You may now restart services."
  line
  pause
  return 0
}

###############################################
# Show Status
###############################################
do_show_status() {
  clear
  line
  echo " MarketSwarm Truth Status"
  line
  echo ""

  if [[ -f "$TRUTH_FILE" ]]; then
    info "truth.json:"
    jq '{version, description, buses: (.buses | keys), components: (.components | keys)}' "$TRUTH_FILE"
    echo ""
  else
    warn "truth.json not found at $TRUTH_FILE"
    echo ""
  fi

  info "Redis buses:"
  echo ""
  show_redis_status
  echo ""

  # Check if truth is loaded
  if [[ -f "$TRUTH_FILE" ]]; then
    readarray -t buses < <(get_redis_buses)
    local system_entry
    system_entry="$(printf "%s\n" "${buses[@]}" | grep "^system-redis|" || true)"

    if [[ -n "$system_entry" ]]; then
      IFS='|' read -r _ _ endpoint <<< "$system_entry"
      local sys_host="${endpoint%%:*}"
      local sys_port="${endpoint##*:}"

      if redis-cli -h "$sys_host" -p "$sys_port" EXISTS truth 2>/dev/null | grep -q '^1$'; then
        success "Truth is loaded in system-redis"
      else
        warn "Truth NOT loaded in system-redis"
      fi
    fi
  fi

  pause
}

###############################################
# Interactive Menu
###############################################
menu() {
  MENU_MODE=true

  while true; do
    clear
    line
    echo " MarketSwarm – Update Truth"
    line
    echo ""
    echo "Steps:"
    echo "  1) Build truth.json"
    echo "  2) Clear Redis buses"
    echo "  3) Load truth into Redis"
    echo ""
    echo "Combined:"
    echo "  4) Full Update (Build → Clear → Load)"
    echo ""
    echo "Info:"
    echo "  5) Show Status"
    echo ""
    echo "  q) Quit"
    echo ""
    line
    read -rp "Choose [1-5,q]: " choice

    case "$choice" in
      1) do_build_truth ;;
      2) do_clear_redis ;;
      3) do_load_truth ;;
      4) do_full_update ;;
      5) do_show_status ;;
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
# CLI Usage
###############################################
usage() {
  cat <<EOF
Usage: $(basename "$0") [command]

Commands:
  build       Build truth.json from component JSONs
  clear       Clear all Redis buses (FLUSHALL)
  load        Load truth.json into system-redis
  update      Full update: build → clear → load (non-interactive)
  status      Show current truth and Redis status

Options:
  -y, --yes   Skip confirmation prompts (for 'update' command)

If no command is given, opens the interactive menu.

Examples:
  $(basename "$0")              # Open menu
  $(basename "$0") build        # Build only
  $(basename "$0") update -y    # Full update, no prompts
  $(basename "$0") status       # Show status
EOF
}

###############################################
# CLI Entrypoint
###############################################
cli_main() {
  local cmd="${1:-}"
  shift || true

  case "$cmd" in
    build)
      check_preconditions || exit 1
      MENU_MODE=false
      do_build_truth
      ;;
    clear)
      MENU_MODE=false
      if [[ "${1:-}" == "-y" || "${1:-}" == "--yes" ]]; then
        do_clear_redis
      else
        read -rp "This will FLUSHALL all Redis buses. Type CLEAR to confirm: " confirm
        [[ "$confirm" == "CLEAR" ]] || { echo "Aborted."; exit 1; }
        do_clear_redis
      fi
      ;;
    load)
      MENU_MODE=false
      do_load_truth
      ;;
    update)
      MENU_MODE=false
      if [[ "${1:-}" != "-y" && "${1:-}" != "--yes" ]]; then
        echo "This will build truth, clear Redis, and load truth."
        read -rp "Continue? [y/N] " confirm
        [[ "$confirm" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 1; }
      fi
      do_full_update
      ;;
    status)
      MENU_MODE=false
      do_show_status
      ;;
    -h|--help|help)
      usage
      ;;
    "")
      menu
      ;;
    *)
      echo "Unknown command: $cmd"
      echo ""
      usage
      exit 1
      ;;
  esac
}

cli_main "$@"
