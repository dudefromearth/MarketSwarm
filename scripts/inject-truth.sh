#!/bin/bash
set -euo pipefail
IFS=$'\n\t'

# ──────────────────────────────────────────────
# 🧠 inject-truth.sh v4.0 — Truth + Lua Synchronizer
# Author: Ernie Varitimos / FatTail Systems
# ──────────────────────────────────────────────
# Seeds and verifies truth:doc and Lua scripts across Redis buses.
# Verifies SHA consistency and readiness for system startup.
# ──────────────────────────────────────────────

# ANSI colors
RESET=$(tput sgr0)
BOLD=$(tput bold)
GREEN='\033[1;32m'
CYAN='\033[1;36m'
YELLOW='\033[1;33m'
RED='\033[1;31m'

# Redis endpoints
SYSTEM_URL="redis://localhost:6379"
MARKET_URL="redis://localhost:6380"
INTEL_URL="redis://localhost:6381"
LUA_FILE="./scripts/lua_diff.lua"
TRUTH_FILE="./truth.json"

# ──────────────────────────────────────────────
# Logging helper
# ──────────────────────────────────────────────
log() {
  local lvl="$1"; shift
  local msg="$*"
  local t; t=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  echo -e "[$t][$lvl] $msg"
}

# ──────────────────────────────────────────────
# Ensure prerequisites
# ──────────────────────────────────────────────
if ! command -v redis-cli >/dev/null 2>&1; then
  log "ERROR" "redis-cli not found. Install Redis CLI before running."
  exit 2
fi

if [[ ! -f "$TRUTH_FILE" ]]; then
  log "ERROR" "Missing truth.json — cannot inject truth."
  exit 2
fi

if [[ ! -f "$LUA_FILE" ]]; then
  log "ERROR" "Missing lua_diff.lua — cannot inject Lua logic."
  exit 2
fi

# ──────────────────────────────────────────────
# Verify Redis health
# ──────────────────────────────────────────────
verify_redis_health() {
  local url="$1"
  local port=$(echo "$url" | awk -F: '{print $3}')
  if redis-cli -u "$url" ping >/dev/null 2>&1; then
    log "OK" "✔ $port healthy"
  else
    log "ERROR" "❌ Redis on $port unreachable"
    exit 2
  fi
}

# ──────────────────────────────────────────────
# Truth injection and verification
# ──────────────────────────────────────────────
inject_truth() {
  local url="$1"
  local port=$(echo "$url" | awk -F: '{print $3}')
  log "INFO" "📤 Injecting truth.json into Redis $port..."
  redis-cli -u "$url" -x SET truth:doc < "$TRUTH_FILE" >/dev/null
  log "OK" "✅ truth:doc injected on $port"
}

verify_truth() {
  local url="$1"
  local port=$(echo "$url" | awk -F: '{print $3}')
  local hash
  hash=$(redis-cli -u "$url" GET truth:doc | sha1sum | awk '{print $1}')
  echo "$hash"
}

# ──────────────────────────────────────────────
# Lua script loading and verification
# ──────────────────────────────────────────────
load_lua() {
  local url="$1"
  local port=$(echo "$url" | awk -F: '{print $3}')
  local sha
  sha=$(redis-cli -u "$url" SCRIPT LOAD "$(cat "$LUA_FILE")" 2>/dev/null || true)

  if [[ -z "$sha" ]]; then
    log "ERROR" "❌ Failed to load Lua script on $port"
    exit 2
  fi

  if redis-cli -u "$url" SCRIPT EXISTS "$sha" | grep -q "1"; then
    log "OK" "✅ Lua script verified (SHA: $sha) on $port"
    echo "$sha"
  else
    log "ERROR" "❌ Lua verification failed on $port"
    exit 2
  fi
}

# ──────────────────────────────────────────────
# Command handling
# ──────────────────────────────────────────────
MODE="${1:-}"

if [[ -z "$MODE" ]]; then
  log "ERROR" "No mode specified. Use --inject or --verify"
  exit 1
fi

log "INFO" "📜 Mode: ${MODE#--}"

# ──────────────────────────────────────────────
# Execute
# ──────────────────────────────────────────────
case "$MODE" in
  --inject)
    for url in "$SYSTEM_URL" "$MARKET_URL" "$INTEL_URL"; do
      verify_redis_health "$url"
      inject_truth "$url"
    done

    log "INFO" "🧮 Verifying truth hash consistency..."
    declare -A truth_hashes
    i=0
    for url in "$SYSTEM_URL" "$MARKET_URL" "$INTEL_URL"; do
      truth_hashes[$i]=$(verify_truth "$url")
      ((i++))
    done

    if [[ "${truth_hashes[0]}" == "${truth_hashes[1]}" && "${truth_hashes[1]}" == "${truth_hashes[2]}" ]]; then
      log "OK" "✅ truth:doc verified (hash match) across all buses"
    else
      log "ERROR" "❌ truth:doc mismatch between buses"
      exit 2
    fi

    log "INFO" "🧩 Loading Lua scripts into all Redis buses..."
    declare -A lua_hashes
    i=0
    for url in "$SYSTEM_URL" "$MARKET_URL" "$INTEL_URL"; do
      lua_hashes[$i]=$(load_lua "$url")
      ((i++))
    done

    if [[ "${lua_hashes[0]}" == "${lua_hashes[1]}" && "${lua_hashes[1]}" == "${lua_hashes[2]}" ]]; then
      log "OK" "✅ Lua script verified (SHA match across all buses)"
    else
      log "ERROR" "❌ Lua script mismatch between buses"
      exit 2
    fi

    log "OK" "✅ All truth and Lua synchronization complete."
    exit 0
    ;;

  --verify)
    for url in "$SYSTEM_URL" "$MARKET_URL" "$INTEL_URL"; do
      verify_redis_health "$url"
    done

    log "INFO" "🧮 Verifying truth hash consistency..."
    declare -A truth_hashes
    i=0
    for url in "$SYSTEM_URL" "$MARKET_URL" "$INTEL_URL"; do
      truth_hashes[$i]=$(verify_truth "$url")
      ((i++))
    done

    if [[ "${truth_hashes[0]}" == "${truth_hashes[1]}" && "${truth_hashes[1]}" == "${truth_hashes[2]}" ]]; then
      log "OK" "✅ truth:doc verified (hash match) across all buses"
    else
      log "ERROR" "❌ truth:doc mismatch between buses"
      exit 2
    fi

    log "INFO" "🧩 Verifying Lua scripts across all Redis buses..."
    declare -A lua_hashes
    i=0
    for url in "$SYSTEM_URL" "$MARKET_URL" "$INTEL_URL"; do
      lua_hashes[$i]=$(load_lua "$url")
      ((i++))
    done

    if [[ "${lua_hashes[0]}" == "${lua_hashes[1]}" && "${lua_hashes[1]}" == "${lua_hashes[2]}" ]]; then
      log "OK" "✅ Lua script verified (SHA match across all buses)"
    else
      log "ERROR" "❌ Lua script mismatch between buses"
      exit 2
    fi

    log "OK" "✅ Redis verification complete — truth and Lua aligned."
    exit 0
    ;;

  *)
    log "ERROR" "Unknown mode: $MODE"
    echo "Usage: $0 [--inject | --verify]"
    exit 1
    ;;
esac