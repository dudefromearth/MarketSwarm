#!/bin/bash
set -e

# ANSI colors
BOLD=$(tput bold)
RESET=$(tput sgr0)
BLUE='\033[1;34m'
GREEN='\033[1;32m'
YELLOW='\033[1;33m'
CYAN='\033[1;36m'
RED='\033[1;31m'

# Default flags
TAIL_MODE=false
FAST_MODE=false
STATUS_MODE=false

# Help message
show_help() {
  echo -e "${BOLD}🐋 MarketSwarm Whale — Full System Rebuild and Launch${RESET}"
  echo ""
  echo -e "${CYAN}Usage:${RESET}  ./whale.sh [options]"
  echo ""
  echo -e "${CYAN}Options:${RESET}"
  echo -e "  ${YELLOW}-t, --tail${RESET}     Launch stack and follow live heartbeats"
  echo -e "  ${YELLOW}-f, --fast${RESET}     Fast restart (reuse existing images, skip prune)"
  echo -e "  ${YELLOW}-s, --status${RESET}   Check system status (no rebuild)"
  echo -e "  ${YELLOW}-h, --help${RESET}     Show this help message and exit"
  echo ""
  echo -e "${CYAN}Examples:${RESET}"
  echo -e "  ./whale.sh                → Full rebuild and launch"
  echo -e "  ./whale.sh --tail         → Full rebuild + tail heartbeats"
  echo -e "  ./whale.sh --fast         → Quick restart, no rebuild"
  echo -e "  ./whale.sh --status       → Check container & Redis health"
  echo ""
}

# Parse arguments
for arg in "$@"; do
  case $arg in
    -t|--tail)   TAIL_MODE=true ;;
    -f|--fast)   FAST_MODE=true ;;
    -s|--status) STATUS_MODE=true ;;
    -h|--help)
      show_help; exit 0 ;;
    *)
      echo "Unknown option: $arg"; show_help; exit 1 ;;
  esac
done

# --- STATUS MODE ---
if [ "$STATUS_MODE" = true ]; then
  echo -e "${BLUE}🔍 MarketSwarm System Status${RESET}"
  echo -e "${CYAN}📦 Containers:${RESET}"
  docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

  echo ""
  echo -e "${CYAN}🩺 Redis Health Checks:${RESET}"
  for redis in system-redis market-redis; do
    if docker exec "$redis" redis-cli ping >/dev/null 2>&1; then
      echo -e "  ${GREEN}${redis}${RESET}: PONG ✅"
    else
      echo -e "  ${RED}${redis}${RESET}: Unreachable ❌"
    fi
  done
  echo ""
  exit 0
fi

echo -e "${BLUE}🐋  MarketSwarm Whale — Full System Rebuild and Launch${RESET}"
echo -e "${CYAN}⚙️  Mode:${RESET} $([[ $TAIL_MODE == true ]] && echo 'Tail Heartbeats' || ([[ $FAST_MODE == true ]] && echo 'Fast Restart' || echo 'Full Rebuild'))"

NETWORK_NAME="marketswarm-bus"

# Step 1 — cleanup
if [ "$FAST_MODE" = false ]; then
  echo -e "${YELLOW}🧹  Cleaning up existing containers and networks...${RESET}"
  docker compose down -v --remove-orphans || true
  echo -e "${YELLOW}🧽  Pruning old images, networks, and volumes...${RESET}"
  docker system prune -af || true
else
  echo -e "${CYAN}⏩  Fast mode: skipping cleanup and rebuild.${RESET}"
fi

# Step 2 — ensure network
if ! docker network inspect $NETWORK_NAME >/dev/null 2>&1; then
  echo -e "${CYAN}🌐  Creating shared network: $NETWORK_NAME${RESET}"
  docker network create $NETWORK_NAME
else
  echo -e "${CYAN}🌐  Network $NETWORK_NAME already exists — reusing.${RESET}"
fi

# Step 3 — rebuild
if [ "$FAST_MODE" = false ]; then
  echo -e "${YELLOW}🏗️  Building fresh images...${RESET}"
  docker compose build --no-cache
fi

# Step 4 — launch
echo -e "${GREEN}🚀  Launching MarketSwarm stack...${RESET}"
docker compose up -d

# Step 5 — Redis health check
echo -e "${CYAN}🩺  Waiting for Redis health...${RESET}"
until [[ $(docker inspect --format='{{.State.Health.Status}}' system-redis 2>/dev/null) == "healthy" && \
        $(docker inspect --format='{{.State.Health.Status}}' market-redis 2>/dev/null) == "healthy" ]]; do
  echo "⏳  Waiting for Redis containers..."
  sleep 2
done
echo -e "${GREEN}✅  Redis cluster healthy.${RESET}"

# Step 6 — list containers
echo -e "${CYAN}🔍  Checking container status...${RESET}"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Step 7 — optional tail
if [ "$TAIL_MODE" = true ]; then
  echo ""
  echo -e "${CYAN}💓  Tailing live heartbeats (Ctrl+C to exit)...${RESET}"
  docker compose logs -f healer mesh rss_agg massive vexy_ai
else
  echo ""
  echo -e "${GREEN}✅  All systems nominal — MarketSwarm is live.${RESET}"
  echo -e "${YELLOW}💡 Tip:${RESET} Run ${CYAN}'./whale.sh -t'${RESET} to monitor live heartbeats."
fi