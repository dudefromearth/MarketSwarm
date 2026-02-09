#!/bin/bash
# =============================================================
# MarketSwarm Promotion Script (Run from Dev Machine)
# =============================================================
# Run this on StudioTwo to promote code to production.
# This script pushes to Git, then triggers deploy on DudeOne.
#
# Usage:
#   ./promote.sh              # Push and deploy
#   ./promote.sh --no-push    # Deploy only (already pushed)
#   ./promote.sh --status     # Check production status
# =============================================================

set -e

# Configuration
PROD_HOST="${PROD_HOST:-DudeOne.local}"
MARKETSWARM_DIR="${MARKETSWARM_DIR:-/Users/ernie/MarketSwarm}"
REMOTE_DEPLOY_SCRIPT="$MARKETSWARM_DIR/deploy/deploy.sh"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

header() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

success() {
    echo -e "${GREEN}✓${NC} $1"
}

warn() {
    echo -e "${YELLOW}⚠${NC} $1"
}

error() {
    echo -e "${RED}✗${NC} $1"
    exit 1
}

git_push() {
    header "Pushing to GitHub"

    cd "$MARKETSWARM_DIR"

    # Check for uncommitted changes
    if [[ -n $(git status --porcelain) ]]; then
        warn "You have uncommitted changes:"
        git status --short
        echo ""
        read -p "Continue anyway? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            error "Commit your changes first"
        fi
    fi

    # Push to origin
    echo "Pushing to origin/main..."
    git push origin main

    success "Pushed to GitHub"
}

deploy_production() {
    header "Deploying to Production ($PROD_HOST)"

    echo "Connecting to $PROD_HOST..."

    # Run deploy script on production server
    ssh "$PROD_HOST" "cd $MARKETSWARM_DIR && ./deploy/deploy.sh"

    success "Production deployment complete"
}

check_status() {
    header "Production Status ($PROD_HOST)"

    ssh "$PROD_HOST" "cd $MARKETSWARM_DIR && ./deploy/deploy.sh --status"
}

show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  (no args)     Push to Git and deploy to production"
    echo "  --no-push     Skip git push, just deploy"
    echo "  --status      Check production service status"
    echo "  --help        Show this help"
    echo ""
    echo "Environment variables:"
    echo "  PROD_HOST         Production server (default: DudeOne.local)"
    echo "  MARKETSWARM_DIR   Path to MarketSwarm (default: /Users/ernie/MarketSwarm)"
}

main() {
    local mode="${1:-full}"

    case "$mode" in
        --help|-h)
            show_usage
            exit 0
            ;;
        --no-push)
            deploy_production
            ;;
        --status)
            check_status
            ;;
        full|"")
            header "MarketSwarm Promotion"
            echo "From: $(hostname) (dev)"
            echo "To: $PROD_HOST (production)"
            echo "Time: $(date)"
            echo ""

            git_push
            deploy_production

            header "Promotion Complete"
            success "Code is now live in production"
            ;;
        *)
            error "Unknown option: $mode"
            ;;
    esac
}

main "$@"
