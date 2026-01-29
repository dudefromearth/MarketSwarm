#!/opt/homebrew/bin/bash
set -euo pipefail

###############################################
# MarketSwarm – Volume Profile Historical Download
# Downloads 15 years of SPY data from Polygon
# Builds initial volume profile bucketed by price
###############################################

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$ROOT/services/massive/intel/volume_profile/vp_download.py"

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
# Check dependencies
###############################################
check_deps() {
  if ! command -v python3 &>/dev/null; then
    log_error "python3 not found"
    exit 1
  fi

  # Check for API key
  if [[ -z "${POLYGON_API_KEY:-}" ]] && [[ -z "${MASSIVE_API_KEY:-}" ]]; then
    log_error "POLYGON_API_KEY or MASSIVE_API_KEY environment variable required"
    log_info "Export your Polygon API key before running:"
    log_info "  export POLYGON_API_KEY=your_key_here"
    exit 1
  fi
}

###############################################
# Main
###############################################
echo
echo "═══════════════════════════════════════════════════════"
echo " MarketSwarm – Volume Profile Historical Download"
echo "═══════════════════════════════════════════════════════"
echo
log_info "This will download 15 years of SPY minute data from Polygon"
log_info "and build a volume profile scaled to SPX price levels."
log_warn "This may take 30-60 minutes depending on API rate limits."
echo
read -p "Press Enter to continue or Ctrl+C to cancel..."
echo

check_deps

cd "$ROOT"
log_info "Starting download..."
echo

python3 "$SCRIPT"

echo
log_ok "Volume profile download complete!"
log_info "Profile stored in Redis at: massive:volume_profile:spx"
