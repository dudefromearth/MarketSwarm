#!/opt/homebrew/bin/bash
set -euo pipefail

###############################################
# MarketSwarm – Truth Builder
# Wrapper for scripts/build_truth.py
###############################################

BREW_PY="/opt/homebrew/bin/python3.14"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPTS_DIR="$ROOT/scripts"
TRUTH_DIR="$ROOT/truth"
COMPONENTS_DIR="$TRUTH_DIR/components"

VENV="$ROOT/.venv"
VENV_PY="$VENV/bin/python"

BUILD_SCRIPT="$SCRIPTS_DIR/build_truth.py"
OUTPUT_TRUTH="$SCRIPTS_DIR/truth.json"

###############################################
# UI Helpers
###############################################
line() { echo "──────────────────────────────────────────────"; }

show_last_truth() {
  clear
  line
  echo " MarketSwarm – Current Composite Truth"
  line
  echo ""
  if [[ -f "$OUTPUT_TRUTH" ]]; then
    jq '{version, description, buses: ( .buses | keys ), components: ( .components | keys )}' "$OUTPUT_TRUTH"
  else
    echo "No truth.json found at: $OUTPUT_TRUTH"
  fi
  echo ""
  read -n 1 -s -r -p "Press any key to return..."
}

run_builder() {
  clear
  line
  echo " MarketSwarm – Running Truth Builder"
  line
  echo "ROOT:        $ROOT"
  echo "VENV_PY:     $VENV_PY"
  echo "BUILD_SCRIPT:$BUILD_SCRIPT"
  echo ""

  # Validate Python
  if [[ ! -x "$VENV_PY" ]]; then
    echo "ERROR: venv python not found at $VENV_PY"
    echo "       Did you create the virtualenv?"
    exit 1
  fi

  if [[ ! -f "$BUILD_SCRIPT" ]]; then
    echo "ERROR: build_truth.py not found at $BUILD_SCRIPT"
    exit 1
  fi

  line
  echo "Executing: $VENV_PY $BUILD_SCRIPT"
  line
  "$VENV_PY" "$BUILD_SCRIPT"
  echo ""
  read -n 1 -s -r -p "Press any key to return to menu..."
}

check_node() {
  local node_file="${1:-"$TRUTH_DIR/mm_node.json"}"

  clear
  line
  echo " MarketSwarm – Validate Node Definition"
  line
  echo "Node file: $node_file"
  echo ""

  if [[ ! -f "$node_file" ]]; then
    echo "ERROR: Node definition not found at: $node_file"
    echo "       Pass an explicit path or create mm_node.json under truth/"
    read -n 1 -s -r -p "Press any key to return..."
    return
  fi

  "$VENV_PY" "$BUILD_SCRIPT" check-node --file "$node_file"
  echo ""
  read -n 1 -s -r -p "Press any key to return..."
}

component_menu() {
  clear
  line
  echo " MarketSwarm – Validate Component Definition"
  line
  echo ""

  if [[ ! -d "$COMPONENTS_DIR" ]]; then
    echo "Components directory not found: $COMPONENTS_DIR"
    read -n 1 -s -r -p "Press any key to return..."
    return
  fi

  mapfile -t comps < <(find "$COMPONENTS_DIR" -maxdepth 1 -type f -name '*.json' | sort)
  if [[ "${#comps[@]}" -eq 0 ]]; then
    echo "No component JSON files found in $COMPONENTS_DIR"
    read -n 1 -s -r -p "Press any key to return..."
    return
  fi

  echo "Available components:"
  echo ""
  local i=1
  for path in "${comps[@]}"; do
    local base
    base="$(basename "$path")"
    local name="${base%.json}"
    printf "  %2d) %s (%s)\n" "$i" "$name" "$base"
    ((i++))
  done
  echo "  q) Cancel"
  echo ""
  read -rp "Select component [1-${#comps[@]} or q]: " sel

  if [[ "$sel" == "q" || "$sel" == "Q" ]]; then
    return
  fi

  if ! [[ "$sel" =~ ^[0-9]+$ ]] || (( sel < 1 || sel > ${#comps[@]} )); then
    echo "Invalid selection"
    sleep 1
    return
  fi

  local chosen="${comps[$((sel-1))]}"
  local base
  base="$(basename "$chosen")"
  local name="${base%.json}"

  clear
  line
  echo " Validating component: $name ($chosen)"
  line
  echo ""

  "$VENV_PY" "$BUILD_SCRIPT" check-component --name "$name"
  echo ""
  read -n 1 -s -r -p "Press any key to return..."
}

check_component_direct() {
  # $1 may be a name or a path
  local arg="${1:-}"

  if [[ -z "$arg" ]]; then
    component_menu
    return
  fi

  if [[ -f "$arg" ]]; then
    # Treat as file path
    "$VENV_PY" "$BUILD_SCRIPT" check-component --file "$arg"
  else
    # Treat as component name
    "$VENV_PY" "$BUILD_SCRIPT" check-component --name "$arg"
  fi
}

###############################################
# Main Menu
###############################################
menu() {
  while true; do
    clear
    line
    echo " MarketSwarm – Truth Builder"
    line
    echo "Select Option:"
    echo ""
    echo "  1) Build Truth (run build_truth.py)"
    echo "  2) View Current Truth Summary"
    echo "  3) Validate Node Definition"
    echo "  4) Validate Component Definition"
    echo "  5) Quit"
    echo ""
    line
    read -rp "Enter choice [1-5]: " CH
    echo ""

    case "$CH" in
      1) run_builder ;;
      2) show_last_truth ;;
      3) check_node ;;
      4) component_menu ;;
      5) echo "Goodbye"; exit 0 ;;
      *) echo "Invalid choice"; sleep 1 ;;
    esac
  done
}

###############################################
# Argument override
###############################################
if [[ $# -gt 0 ]]; then
  case "$1" in
    --build)
      # Non-interactive build — no clear, no keypress waits.
      # Use this from scripts, CI, or automated contexts.
      if [[ ! -x "$VENV_PY" ]]; then
        echo "ERROR: venv python not found at $VENV_PY" >&2
        exit 1
      fi
      if [[ ! -f "$BUILD_SCRIPT" ]]; then
        echo "ERROR: build_truth.py not found at $BUILD_SCRIPT" >&2
        exit 1
      fi
      "$VENV_PY" "$BUILD_SCRIPT"
      exit $?
      ;;
    run)
      run_builder
      exit 0
      ;;
    show)
      show_last_truth
      exit 0
      ;;
    check-node)
      # Optional second arg: path to node file
      NODE_FILE="${2:-"$TRUTH_DIR/mm_node.json"}"
      check_node "$NODE_FILE"
      exit 0
      ;;
    check-comp)
      # Optional second arg: name or path
      ARG="${2:-}"
      check_component_direct "$ARG"
      exit 0
      ;;
    *)
      echo "Usage: $0 [--build|run|show|check-node [node.json]|check-comp [name|component.json]]"
      echo ""
      echo "  --build     Build truth non-interactively (for scripts/automation)"
      echo "  run         Build truth (interactive, with menu return)"
      echo "  show        View current truth summary"
      echo "  check-node  Validate node definition"
      echo "  check-comp  Validate a component definition"
      echo ""
      echo "No arguments launches the interactive menu."
      exit 1
      ;;
  esac
else
  menu
fi