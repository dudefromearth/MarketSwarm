#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

# ──────────────────────────────────────────────
# 🧠 setup-host.sh v4.3 — Modern Environment Auditor
# Author: FatTail Systems / MarketSwarm
# ──────────────────────────────────────────────
# Verifies Bash ≥5.0, Docker Compose plugin linkage,
# and core developer tools across macOS and Linux hosts.
# ──────────────────────────────────────────────

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
}

check_version() {
  local tool="$1"
  local required="$2"
  local current
  current=$($tool --version 2>/dev/null | head -n1 | grep -oE '[0-9]+\.[0-9]+(\.[0-9]+)?' | head -n1)
  if [[ -z "$current" ]]; then
    log "ERROR" "❌ $tool not found"
    return 1
  fi
  if [[ "$(printf '%s\n' "$required" "$current" | sort -V | head -n1)" == "$required" ]]; then
    log "OK" "✅ $tool $current (≥$required)"
  else
    log "ERROR" "❌ $tool version $current < required $required"
    return 1
  fi
}

# ──────────────────────────────────────────────
# Verify Bash ≥5.0
# ──────────────────────────────────────────────
BASH_PATH="$(command -v bash || true)"
if [[ -z "$BASH_PATH" ]]; then
  log "ERROR" "❌ Bash not found in PATH."
  exit 2
fi

check_version bash 5.0 || exit 2

if ! grep -q "$BASH_PATH" /etc/shells; then
  log "WARN" "⚠️ $BASH_PATH not listed in /etc/shells — adding..."
  echo "$BASH_PATH" | sudo tee -a /etc/shells >/dev/null
fi

if [[ "$SHELL" != "$BASH_PATH" ]]; then
  log "INFO" "🔁 Switching default shell to $BASH_PATH..."
  chsh -s "$BASH_PATH"
fi

# ──────────────────────────────────────────────
# Verify Docker & Compose
# ──────────────────────────────────────────────
if ! command -v docker >/dev/null; then
  log "ERROR" "❌ Docker CLI missing."
  exit 2
fi
check_version docker 27.0

if ! docker compose version >/dev/null 2>&1; then
  log "WARN" "⚠️ docker compose plugin missing — checking linkage..."
  COMPOSE_SRC="/Applications/Docker.app/Contents/Resources/cli-plugins/docker-compose"
  PLUGIN_DIR="/usr/local/lib/docker/cli-plugins"
  if [[ -f "$COMPOSE_SRC" ]]; then
    sudo mkdir -p "$PLUGIN_DIR"
    sudo ln -sf "$COMPOSE_SRC" "$PLUGIN_DIR/docker-compose"
    log "OK" "✅ Linked Docker Compose CLI plugin"
  else
    log "ERROR" "❌ docker-compose binary not found at $COMPOSE_SRC"
    exit 2
  fi
else
  log "OK" "✅ Docker Compose plugin functional"
fi

# ──────────────────────────────────────────────
# Verify core utilities
# ──────────────────────────────────────────────
for tool in jq curl git redis-cli; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    log "WARN" "⚠️ Missing $tool — installing via Homebrew..."
    brew install "$tool"
  else
    log "OK" "✅ $tool present"
  fi
done

# ──────────────────────────────────────────────
# Summary
# ──────────────────────────────────────────────
echo "─────────────────────────────────────────────"
log "OK" "✅ Host environment verified."
echo "Bash Path:    $BASH_PATH"
echo "Default Shell: $SHELL"
echo "Docker:       $(docker --version | head -n1)"
echo "Compose:      $(docker compose version | head -n1)"
echo "Redis CLI:    $(redis-cli --version)"
echo "─────────────────────────────────────────────"
log "OK" "System is ready for Whale, inject-truth, and Redis orchestration."