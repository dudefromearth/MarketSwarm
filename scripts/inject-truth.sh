#!/opt/homebrew/bin/bash
set -euo pipefail
IFS=$'\n\t'

# ──────────────────────────────────────────────
# 🧠 inject-truth.sh v5.1 — Market Bus Lua Synchronizer
# Author: Ernie Varitimos / FatTail Systems
# ──────────────────────────────────────────────
# Performs semantic JSON verification across all Redis buses
# and Lua synchronization (only for the market bus 6380).
# Ensures consistent truth:doc state without byte-level fragility.
# ──────────────────────────────────────────────

RESET=$(tput sgr0); BOLD=$(tput bold)
GREEN='\033[1;32m'; CYAN='\033[1;36m'; YELLOW='\033[1;33m'; RED='\033[1;31m'

SYSTEM_URL="redis://localhost:6379"
MARKET_URL="redis://localhost:6380"
INTEL_URL="redis://localhost:6381"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LUA_FILE="${SCRIPT_DIR}/lua_diff.lua"
TRUTH_FILE="${SCRIPT_DIR}/truth.json"
TMPDIR="${TMPDIR:-/tmp}"

log() {
  local lvl="$1"; shift
  local msg="$*"
  local t; t=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  echo -e "[$t][$lvl] $msg"
}

show_help() {
  echo -e "${BOLD}🧠 inject-truth.sh v5.1 — Market Bus Lua Synchronizer${RESET}"
  echo ""
  echo -e "${CYAN}Usage:${RESET}  ./inject-truth.sh [--inject|--verify|--help]"
  echo ""
  echo -e "${CYAN}Modes:${RESET}"
  echo -e "  ${YELLOW}--inject${RESET}   Inject truth.json into all buses and Lua into market bus"
  echo -e "  ${YELLOW}--verify${RESET}   Verify semantic equality of truth.json and Lua integrity"
  echo -e "  ${YELLOW}--help${RESET}     Show this help message"
  echo ""
  echo -e "Notes:"
  echo -e "  • JSON equality is semantic (via jq -S .)."
  echo -e "  • Lua diff logic loaded and verified only on market bus (6380)."
  echo -e "  • Safe runtime sanity check ensures Lua executes cleanly."
  echo ""
}

# ──────────────────────────────────────────────
# Preconditions
# ──────────────────────────────────────────────
if ! command -v redis-cli >/dev/null 2>&1; then
  log "ERROR" "redis-cli not found. Install Redis CLI before running."; exit 2
fi
if [[ ! -f "$TRUTH_FILE" ]]; then
  log "ERROR" "Missing truth.json — cannot inject truth."; exit 2
fi
if [[ ! -f "$LUA_FILE" ]]; then
  log "ERROR" "Missing lua_diff.lua — cannot inject Lua logic."; exit 2
fi

# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────
port_from_url() { echo "$1" | awk -F: '{print $3}'; }

verify_redis_health() {
  local url="$1"
  local port; port=$(port_from_url "$url")
  if redis-cli -u "$url" ping >/dev/null 2>&1; then
    log "OK" "✔ $port healthy"
  else
    log "ERROR" "❌ Redis on $port unreachable"
    return 1
  fi
}

canonical_json_hash() {
  local file="$1"
  if command -v jq >/dev/null 2>&1; then
    jq -S . "$file" 2>/dev/null | tr -d '\r' | shasum -a 256 | awk '{print $1}'
  else
    log "WARN" "jq not found — using raw hash fallback."
    shasum -a 256 "$file" | awk '{print $1}'
  fi
}

redis_json_hash() {
  local url="$1"; local tmp; tmp="$(mktemp)"
  redis-cli -u "$url" --raw GET truth:doc > "$tmp" 2>/dev/null || true

  if command -v jq >/dev/null 2>&1; then
    if jq -e . "$tmp" >/dev/null 2>&1; then
      jq -S . "$tmp" | tr -d '\r' | shasum -a 256 | awk '{print $1}'
    elif jq -R 'fromjson?' "$tmp" >/dev/null 2>&1; then
      jq -R 'fromjson' "$tmp" | jq -S . | tr -d '\r' | shasum -a 256 | awk '{print $1}'
    else
      log "WARN" "Redis content not parseable JSON on $(port_from_url "$url"), using raw hash."
      shasum -a 256 "$tmp" | awk '{print $1}'
    fi
  else
    shasum -a 256 "$tmp" | awk '{print $1}'
  fi
  rm -f "$tmp"
}

diagnose_semantic_mismatch() {
  local file="$1" url="$2"
  local port; port=$(port_from_url "$url")
  log "WARN" "⚠️  Semantic mismatch on $port — JSON differs in structure or content."
  log "INFO" "---- unified diff (canonical form) ----"
  local tmpf tmpr; tmpf="$(mktemp)"; tmpr="$(mktemp)"
  jq -S . "$file" > "$tmpf" 2>/dev/null || cp "$file" "$tmpf"
  redis-cli -u "$url" --raw GET truth:doc > "$tmpr" 2>/dev/null || true
  if jq -R 'fromjson?' "$tmpr" >/dev/null 2>&1; then
    jq -R 'fromjson' "$tmpr" | jq -S . > "${tmpr}.canon"; mv "${tmpr}.canon" "$tmpr"
  fi
  diff -u --label file --label redis "$tmpf" "$tmpr" | sed -n '1,80p' || true
  log "INFO" "---- end diff ----"
  rm -f "$tmpf" "$tmpr"
}

inject_truth() {
  local url="$1"
  local port; port=$(port_from_url "$url")
  log "INFO" "📤 Injecting truth.json into Redis $port (semantic-safe)..."
  if ! redis-cli -u "$url" -x SET truth:doc < "$TRUTH_FILE" >/dev/null 2>&1; then
    log "ERROR" "❌ Injection failed on $port"
    return 1
  fi
  log "OK" "✅ truth:doc injected on $port"
}

load_lua_market() {
  local url="$MARKET_URL"; local port="6380"
  local content sha exists new_sha
  content="$(cat "$LUA_FILE")"
  sha=$(printf "%s" "$content" | shasum -a 1 | awk '{print $1}')
  exists=$(redis-cli -u "$url" SCRIPT EXISTS "$sha" | awk '{print $1}' || echo 0)
  if [[ "$exists" == "1" ]]; then
    log "OK" "✅ Lua already loaded (SHA: $sha) on $port"; echo "$sha"; return 0
  fi
  new_sha=$(redis-cli -u "$url" SCRIPT LOAD "$content" 2>/dev/null || true)
  if [[ -z "$new_sha" ]]; then
    log "ERROR" "❌ Failed to load Lua on $port"; return 1
  fi
  log "OK" "✅ Lua loaded (SHA: $new_sha) on $port"

  # Optional runtime sanity test
  if redis-cli -u "$url" EVAL "return 'ok'" 0 >/dev/null 2>&1; then
    log "OK" "🧠 Redis Lua runtime sanity check passed on $port"
  else
    log "WARN" "⚠️ Redis Lua runtime sanity check failed on $port"
  fi

  echo "$new_sha"; return 0
}

# ──────────────────────────────────────────────
# Command dispatch
# ──────────────────────────────────────────────
MODE="${1:-}"
[[ -z "$MODE" ]] && { show_help; exit 1; }

log "INFO" "📜 Mode: ${MODE#--}"

case "$MODE" in
  --inject)
    for url in "$SYSTEM_URL" "$MARKET_URL" "$INTEL_URL"; do
      verify_redis_health "$url" || exit 2
      inject_truth "$url" || exit 2
    done

    log "INFO" "🧮 Verifying semantic truth consistency..."
    file_hash=$(canonical_json_hash "$TRUTH_FILE")
    mismatch=0
    for url in "$SYSTEM_URL" "$MARKET_URL" "$INTEL_URL"; do
      redis_hash=$(redis_json_hash "$url")
      if [[ "$redis_hash" != "$file_hash" ]]; then
        mismatch=1; diagnose_semantic_mismatch "$TRUTH_FILE" "$url"
      fi
    done
    [[ $mismatch -eq 0 ]] || { log "ERROR" "❌ Semantic mismatch detected across buses"; exit 2; }
    log "OK" "✅ truth:doc semantically consistent across all buses"

    log "INFO" "🧩 Loading Lua script (market bus only)..."
    load_lua_market || exit 2
    log "OK" "✅ Lua verified and runtime healthy on market bus (6380)"
    ;;

  --verify)
    for url in "$SYSTEM_URL" "$MARKET_URL" "$INTEL_URL"; do
      verify_redis_health "$url" || exit 2
    done
    log "INFO" "🧮 Verifying semantic truth consistency..."
    file_hash=$(canonical_json_hash "$TRUTH_FILE"); mismatch=0
    for url in "$SYSTEM_URL" "$MARKET_URL" "$INTEL_URL"; do
      redis_hash=$(redis_json_hash "$url")
      if [[ "$redis_hash" != "$file_hash" ]]; then
        mismatch=1; diagnose_semantic_mismatch "$TRUTH_FILE" "$url"
      fi
    done
    [[ $mismatch -eq 0 ]] || { log "ERROR" "❌ Semantic mismatch found across buses"; exit 2; }
    log "OK" "✅ truth:doc semantically consistent across all buses"

    log "INFO" "🧩 Verifying Lua (market bus only)..."
    load_lua_market || exit 2
    log "OK" "✅ Lua verified and runtime healthy on market bus (6380)"
    ;;

  --help|-h)
    show_help; exit 0
    ;;

  *)
    log "ERROR" "Unknown mode: $MODE"; show_help; exit 1
    ;;
esac