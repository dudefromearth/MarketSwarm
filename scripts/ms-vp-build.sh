#!/opt/homebrew/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOOLS="$ROOT/services/massive/tools"
PY="$ROOT/.venv/bin/python"

VP_BUILDER="$TOOLS/build_volume_profile.py"
VP_PLOTTER="$TOOLS/plot_volume_profile.py"

line() { echo "──────────────────────────────────────────────────"; }

menu() {
  clear
  line
  echo "   SPX Volume Profile Builder"
  line
  echo "1) Build full SPY→SPX profile"
  echo "2) Resume interrupted build"
  echo "3) Plot current profile (enter strike range)"
  echo "4) Export current profile to JSON"
  echo "5) Clear profile (delete redis keys)"
  echo "6) Quit"
  line
  read -rp "Choice: " CH

  case "$CH" in
    1) build_full ;;
    2) resume_chk ;;
    3) plot_range ;;
    4) export_json ;;
    5) clear_profile ;;
    6) exit 0 ;;
  esac
}

build_full() {
  clear
  line
  echo "Running full build (this may take minutes)…"
  line
  $PY "$VP_BUILDER"
  read -n1 -p "Done. Press any key…"
  menu
}

resume_chk() {
  clear
  line
  echo "Resuming build from checkpoint…"
  line
  $PY "$VP_BUILDER"
  read -n1 -p "Resume complete. Press any key…"
  menu
}

plot_range() {
  read -rp "Min SPX strike: " MIN
  read -rp "Max SPX strike: " MAX
  $PY "$VP_PLOTTER" --min "$MIN" --max "$MAX"
  read -n1 -p "Plot done. Press any key…"
  menu
}

export_json() {
  redis-cli -p 6380 HGETALL volume_profile:SPX:bins > volume_profile_export.txt
  echo "Exported to volume_profile_export.txt"
  read -n1 -p "Press any key…"
  menu
}

clear_profile() {
  redis-cli -p 6380 DEL volume_profile:SPX:bins
  redis-cli -p 6380 DEL volume_profile:SPX:meta
  redis-cli -p 6380 DEL volume_profile:SPX:checkpoint
  echo "Cleared."
  read -n1 -p "Press any key…"
  menu
}

menu