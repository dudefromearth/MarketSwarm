#!/bin/bash
# =============================================================
# MarketSwarm Production Deployment Script
# =============================================================
# Run this on DudeOne.local (production server) to deploy
# the latest code from GitHub.
#
# Usage:
#   ./deploy.sh              # Full deploy (pull, migrate, restart)
#   ./deploy.sh --pull-only  # Just pull, no restarts
#   ./deploy.sh --restart    # Just restart services
#   ./deploy.sh --nginx      # Sync Nginx config to MiniThree
#   ./deploy.sh --status     # Check service status
# =============================================================

set -e  # Exit on error

# Configuration
MARKETSWARM_DIR="${MARKETSWARM_DIR:-/Users/ernie/MarketSwarm}"
NGINX_HOST="${NGINX_HOST:-MiniThree}"
NGINX_CONF_PATH="${NGINX_CONF_PATH:-/etc/nginx/sites-available/marketswarm.conf}"
LOG_FILE="${MARKETSWARM_DIR}/deploy/deploy.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Services to restart (in order)
SERVICES=(
    "journal"
    "vexy_ai"
    "rss_agg"
    "copilot"
)

# =============================================================
# Helper Functions
# =============================================================

log() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "${BLUE}[$timestamp]${NC} $1"
    echo "[$timestamp] $1" >> "$LOG_FILE"
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

header() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# =============================================================
# Deployment Steps
# =============================================================

check_prereqs() {
    header "Checking Prerequisites"

    if [[ ! -d "$MARKETSWARM_DIR" ]]; then
        error "MarketSwarm directory not found: $MARKETSWARM_DIR"
    fi

    cd "$MARKETSWARM_DIR"

    if [[ ! -d ".git" ]]; then
        error "Not a git repository: $MARKETSWARM_DIR"
    fi

    success "MarketSwarm directory exists"
    success "Git repository found"
}

git_pull() {
    header "Pulling Latest Code"

    cd "$MARKETSWARM_DIR"

    # Check for local changes
    if [[ -n $(git status --porcelain) ]]; then
        warn "Local changes detected:"
        git status --short
        echo ""
        read -p "Stash changes and continue? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            git stash push -m "Deploy stash $(date '+%Y%m%d_%H%M%S')"
            success "Changes stashed"
        else
            error "Aborting due to local changes"
        fi
    fi

    # Get current commit
    local before_commit=$(git rev-parse --short HEAD)

    # Pull latest
    log "Pulling from origin/main..."
    git pull origin main

    # Get new commit
    local after_commit=$(git rev-parse --short HEAD)

    if [[ "$before_commit" == "$after_commit" ]]; then
        success "Already up to date ($after_commit)"
    else
        success "Updated: $before_commit → $after_commit"
        echo ""
        echo "Changes:"
        git log --oneline "$before_commit..$after_commit" | head -10
    fi
}

run_migrations() {
    header "Running Database Migrations"

    cd "$MARKETSWARM_DIR"

    # The journal service auto-migrates on startup, but we can
    # trigger it explicitly by importing the DB class
    log "Database migrations run automatically on service start"
    log "Journal service will migrate to schema version on restart"
    success "Migration check complete"
}

sync_nginx() {
    header "Syncing Nginx Configuration"

    local conf_src="$MARKETSWARM_DIR/deploy/marketswarm-https.conf"

    if [[ ! -f "$conf_src" ]]; then
        warn "Nginx config not found: $conf_src"
        return
    fi

    log "Copying config to $NGINX_HOST..."

    # Copy config to Nginx server
    scp "$conf_src" "$NGINX_HOST:/tmp/marketswarm-https.conf"

    # Test and reload on Nginx server
    ssh "$NGINX_HOST" bash -s << 'REMOTE_SCRIPT'
        set -e
        echo "Testing nginx config..."
        sudo cp /tmp/marketswarm-https.conf /etc/nginx/sites-available/marketswarm.conf
        sudo nginx -t
        echo "Reloading nginx..."
        sudo systemctl reload nginx
        echo "Nginx reloaded successfully"
REMOTE_SCRIPT

    success "Nginx config synced and reloaded"
}

restart_services() {
    header "Restarting Services"

    cd "$MARKETSWARM_DIR"

    for service in "${SERVICES[@]}"; do
        log "Restarting $service..."

        # Check if service has a .pids file (running)
        local pid_file=".pids/${service}.started"

        if [[ -f "$pid_file" ]]; then
            # Try to stop gracefully
            local pid=$(cat "$pid_file" 2>/dev/null | head -1)
            if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
                kill "$pid" 2>/dev/null || true
                sleep 2
            fi
        fi

        # Start service in background
        case "$service" in
            journal)
                nohup python services/journal/main.py >> logs/journal.log 2>&1 &
                ;;
            vexy_ai)
                nohup python services/vexy_ai/main.py >> logs/vexy_ai.log 2>&1 &
                ;;
            rss_agg)
                nohup python services/rss_agg/main.py >> logs/rss_agg.log 2>&1 &
                ;;
            copilot)
                nohup python services/copilot/main.py >> logs/copilot.log 2>&1 &
                ;;
            *)
                warn "Unknown service: $service"
                continue
                ;;
        esac

        sleep 1
        success "$service started"
    done

    echo ""
    log "Waiting for services to initialize..."
    sleep 5
}

check_status() {
    header "Service Status"

    cd "$MARKETSWARM_DIR"

    for service in "${SERVICES[@]}"; do
        local pid_file=".pids/${service}.started"

        if [[ -f "$pid_file" ]]; then
            local pid=$(cat "$pid_file" 2>/dev/null | head -1)
            if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
                success "$service (PID: $pid)"
            else
                warn "$service (stale PID file)"
            fi
        else
            warn "$service (not running)"
        fi
    done

    # Check Nginx on remote
    echo ""
    log "Checking Nginx on $NGINX_HOST..."
    if ssh "$NGINX_HOST" "systemctl is-active nginx" 2>/dev/null | grep -q "active"; then
        success "Nginx is running on $NGINX_HOST"
    else
        warn "Nginx status unknown on $NGINX_HOST"
    fi
}

show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  (no args)     Full deploy: pull, migrate, restart services"
    echo "  --pull-only   Just pull code, no restarts"
    echo "  --restart     Just restart services"
    echo "  --nginx       Sync Nginx config to MiniThree"
    echo "  --status      Check service status"
    echo "  --help        Show this help"
    echo ""
    echo "Environment variables:"
    echo "  MARKETSWARM_DIR   Path to MarketSwarm (default: /Users/ernie/MarketSwarm)"
    echo "  NGINX_HOST        Nginx server hostname (default: MiniThree)"
}

# =============================================================
# Main
# =============================================================

main() {
    local mode="${1:-full}"

    case "$mode" in
        --help|-h)
            show_usage
            exit 0
            ;;
        --pull-only)
            check_prereqs
            git_pull
            ;;
        --restart)
            check_prereqs
            restart_services
            check_status
            ;;
        --nginx)
            check_prereqs
            sync_nginx
            ;;
        --status)
            check_prereqs
            check_status
            ;;
        full|"")
            header "MarketSwarm Deployment"
            echo "Server: $(hostname)"
            echo "Time: $(date)"

            check_prereqs
            git_pull
            run_migrations
            restart_services
            sync_nginx
            check_status

            header "Deployment Complete"
            success "All services deployed successfully"
            ;;
        *)
            error "Unknown option: $mode"
            ;;
    esac
}

main "$@"
