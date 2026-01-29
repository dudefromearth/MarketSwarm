#!/usr/bin/env bash
# view-tiles.sh
# Simple wrapper to run the heatmap visualizer

set -euo pipefail

# Project root
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TOOL="$ROOT/services/mmaker/tools/heatmap_vis.py"

if [[ ! -f "$TOOL" ]]; then
  echo "Error: heatmap_vis.py not found at $TOOL"
  exit 1
fi

# Pass all arguments directly to the Python tool
cd "$ROOT"
./.venv/bin/python "$TOOL" "$@"