#!/bin/bash
set -euo pipefail
IFS=$'\n\t'

# ──────────────────────────────────────────────
# 🧭 setup-hosts.sh — MarketSwarm Host Verifier
# Author: Ernie Varitimos / FatTail Systems
# ──────────────────────────────────────────────
# Verifies and standardizes host environment for MarketSwarm deployment
# Ensures Xcode tools, Homebrew, jq, curl, git, Docker, and Compose are healthy
# ──────────────────────────────────────────────

LOG_FILE="setup-hosts.log"
BOLD=$(tput bold)
RESET=$(tput sgr0)
GREEN='\033[1;32m'
CYAN='\033[1;36m'
YELLOW='\033[1;33m'
RED='\033[1;31m'

log() {
  local lvl="$1"; shift
  local msg="$*"
  local t; t=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  echo -e "[$t][$lvl] $msg"
  echo "[$t][$lvl] $msg" >> "$LOG_FILE"
}

echo -e "${BOLD}🧭 MarketSwarm Host Setup — Environment Verification${RESET}"
echo "Log file: $LOG_FILE"
echo "─────────────────────────────────────────────"

# ──────────────────────────────────────────────
# Step 1 — Command-line Tools
# ──────────────────────────────────────────────
if ! xcode-select -p >/dev/null 2>&1; then
  log INFO "📦 Installing Xcode Command Line Tools..."
  xcode-select --install || log WARN "⚠️  Manual installation may be required."
else
  log OK "✅ Xcode Command Line Tools detected."
fi

# ──────────────────────────────────────────────
# Step 2 — Homebrew check
# ──────────────────────────────────────────────
if ! command -v brew >/dev/null 2>&1; then
  log INFO "📦 Installing Homebrew..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
else
  log OK "✅ Homebrew installed."
fi

log INFO "🔄 Updating Homebrew and installing prerequisites..."
brew update >/dev/null
brew install jq curl git >/dev/null
log OK "✅ Core packages (jq, curl, git) verified."

# ──────────────────────────────────────────────
# Step 3 — Docker Desktop presence
# ──────────────────────────────────────────────
if [ ! -d "/Applications/Docker.app" ]; then
  log ERROR "❌ Docker Desktop not found. Please install from https://www.docker.com/products/docker-desktop/"
  exit 1
fi
log OK "✅ Docker Desktop application detected."

# ──────────────────────────────────────────────
# Step 4 — Compose Plugin link
# ──────────────────────────────────────────────
PLUGIN_DIR="/usr/local/lib/docker/cli-plugins"
SOURCE_PLUGIN="/Applications/Docker.app/Contents/Resources/cli-plugins/docker-compose"
TARGET_PLUGIN="$PLUGIN_DIR/docker-compose"

sudo mkdir -p "$PLUGIN_DIR"
if [ ! -L "$TARGET_PLUGIN" ]; then
  log INFO "🔗 Linking docker-compose plugin..."
  sudo ln -s "$SOURCE_PLUGIN" "$TARGET_PLUGIN"
else
  log OK "✅ docker-compose plugin link already exists."
fi

# ──────────────────────────────────────────────
# Step 5 — Docker verification
# ──────────────────────────────────────────────
if ! command -v docker >/dev/null 2>&1; then
  log ERROR "❌ docker CLI not found in PATH. Please restart your shell after installing Docker."
  exit 1
fi

log INFO "🧠 Checking Docker engine and Compose integration..."
docker version || { log ERROR "❌ Docker engine not responding."; exit 1; }
docker compose version || { log ERROR "❌ docker compose command failed."; exit 1; }

# ──────────────────────────────────────────────
# Step 6 — Hello-world validation
# ──────────────────────────────────────────────
TEST_DIR="$HOME/compose-test"
mkdir -p "$TEST_DIR"
cd "$TEST_DIR"
echo 'services:
  hello:
    image: hello-world' > docker-compose.yml

log INFO "🚀 Running hello-world container test..."
if docker compose up --quiet-pull; then
  log OK "✅ Docker Compose functional."
else
  log ERROR "❌ Compose test failed."
  exit 1
fi

# ──────────────────────────────────────────────
# Step 7 — Summary
# ──────────────────────────────────────────────
echo "─────────────────────────────────────────────"
log OK "🎯 Host verified and ready for MarketSwarm deployment."
log INFO "📜 All results logged to $LOG_FILE"
echo -e "${GREEN}${BOLD}✅ Setup complete — this host is MarketSwarm-ready.${RESET}"
echo "─────────────────────────────────────────────"