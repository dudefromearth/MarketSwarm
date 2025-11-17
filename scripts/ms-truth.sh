#!/opt/homebrew/bin/bash
# ms-truth.sh — MarketSwarm bootstrap, MUST-verify (truth + lua), and reset
# Usage: ./ms-truth.sh {init|load|status|st|reset|clean|purge|help}
set -euo pipefail

# --- Project root & env ---------------------------------------------------------
# Resolve project root based on script location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MS_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Source ms-busses.env from project root (same source of truth as ms-busses.sh)
if [[ -f "${MS_ROOT}/ms-busses.env" ]]; then
  # shellcheck source=/dev/null
  source "${MS_ROOT}/ms-busses.env"
else
  echo "[ERROR] ms-busses.env not found at ${MS_ROOT}/ms-busses.env" >&2
  exit 1
fi

# Use the Homebrew redis-cli defined in ms-busses.env, no shell PATH reliance
REDIS_CLI="${REDIS_CLI_PATH}"

# Wire system + market Redis to the SAME values ms-busses.sh uses
SYSTEM_REDIS_URL=""
SYSTEM_REDIS_HOST="127.0.0.1"
SYSTEM_REDIS_PORT="${REDIS_SYSTEM_PORT}"
SYSTEM_REDIS_DB=0
SYSTEM_REDIS_PASS="${REDIS_SYSTEM_PASS}"

MARKET_REDIS_URL=""
MARKET_REDIS_HOST="127.0.0.1"
MARKET_REDIS_PORT="${REDIS_MARKET_PORT}"
MARKET_REDIS_DB=0
MARKET_REDIS_PASS="${REDIS_MARKET_PASS}"

# Truth + Lua paths come straight from ms-busses.env
TRUTH_FILE="${TRUTH_JSON_PATH}"
LUA_FILE="${LUA_DIFF_PATH}"
TRUTH_KEY="${TRUTH_KEY:-truth}"

# --- Utils ----------------------------------------------------------------------
log() { printf "%s\n" "$*"; }
err() { printf "[ERROR] %s\n" "$*" >&2; }
die() { err "$*"; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

sha1_of_file() {
  local f="$1"
  if   have shasum;  then shasum -a 1 "$f" | awk '{print tolower($1)}'
  elif have sha1sum; then sha1sum "$f" | awk '{print tolower($1)}'
  elif have openssl; then openssl dgst -sha1 "$f" | awk '{print tolower($NF)}'
  else die "Need shasum/sha1sum/openssl to compute SHA1."
  fi
}

rc_system() {
  if [[ -n "$SYSTEM_REDIS_URL" ]]; then "$REDIS_CLI" -u "$SYSTEM_REDIS_URL" "$@"
  else
    local a=( -h "$SYSTEM_REDIS_HOST" -p "$SYSTEM_REDIS_PORT" -n "$SYSTEM_REDIS_DB" )
    [[ -n "$SYSTEM_REDIS_PASS" ]] && a+=( -a "$SYSTEM_REDIS_PASS" )
    "$REDIS_CLI" "${a[@]}" "$@"
  fi
}

rc_market() {
  if [[ -n "$MARKET_REDIS_URL" ]]; then "$REDIS_CLI" -u "$MARKET_REDIS_URL" "$@"
  else
    local a=( -h "$MARKET_REDIS_HOST" -p "$MARKET_REDIS_PORT" -n "$MARKET_REDIS_DB" )
    [[ -n "$MARKET_REDIS_PASS" ]] && a+=( -a "$MARKET_REDIS_PASS" )
    "$REDIS_CLI" "${a[@]}" "$@"
  fi
}

supports_redisjson() { rc_system COMMAND EXISTS JSON.GET >/dev/null 2>&1; }

# --------------------------------------------------------------------
# 🔥 **REPLACED load_truth() — using the working ms-truth-test.sh logic**
# --------------------------------------------------------------------
load_truth() {
  # Fail if missing file
  [[ -f "$TRUTH_FILE" ]] || die "Missing $TRUTH_FILE"

  local HOST="127.0.0.1"
  local PORT="${SYSTEM_REDIS_PORT}"
  local DB=0
  local KEY="${TRUTH_KEY}"
  local TRUTH_PATH="${TRUTH_FILE}"

  log "Loading truth from: ${TRUTH_PATH}"
  log "Into Redis: ${HOST}:${PORT}, DB=${DB}, Key=${KEY}"

  # Always use raw SET with exact file content
  ${REDIS_CLI} -h "${HOST}" -p "${PORT}" -n "${DB}" SET "${KEY}" "$(cat "${TRUTH_PATH}")" >/dev/null \
    || die "SET failed during truth load"

  log "Truth load complete."

  # Verify load
  log "Verifying truth key..."

  local REDIS_VAL
  local FILE_VAL
  REDIS_VAL="$(${REDIS_CLI} -h "${HOST}" -p "${PORT}" -n "${DB}" GET "${KEY}")"
  FILE_VAL="$(cat "${TRUTH_PATH}")"

  if [[ -z "${REDIS_VAL}" ]]; then
    die "truth key NOT present in Redis"
  fi

  if [[ "${REDIS_VAL}" == "${FILE_VAL}" ]]; then
    log "[OK] truth value matches truth.json exactly."
  else
    die "truth value does NOT match truth.json"
  fi

  # Endpoint sanity check
  local PING_OUT
  PING_OUT="$(${REDIS_CLI} -h "${HOST}" -p "${PORT}" -n "${DB}" PING 2>/dev/null || true)"

  if [[ "${PING_OUT}" == "PONG" ]]; then
    log "[OK] Endpoint responsive (PONG)."
  else
    die "Endpoint NOT responsive"
  fi
}

# --- EVERYTHING BELOW HERE IS UNCHANGED ----------------------------------------

load_lua() {
  [[ -f "$LUA_FILE" ]] || die "Missing $LUA_FILE"
  log "Loading lua_diff into market-redis from ${LUA_FILE}..."
  local sha
  sha=$(rc_market SCRIPT LOAD "$(cat "$LUA_FILE")")
  log "lua_diff: LOADED (SHA $sha) in market-redis"
}

verify_truth() {
  [[ -f "$TRUTH_FILE" ]] || die "Missing $TRUTH_FILE"
  if [[ "$(rc_system EXISTS "$TRUTH_KEY")" != "1" ]]; then
    log "truth: MISSING in system-redis"
    return 1
  fi
  # (Deep verifier unchanged)
  local file_json
  file_json="$(cat "$TRUTH_FILE")"
  local lua='
    local function kind(v)
      if type(v) ~= "table" then return "scalar" end
      local n = #v
      for i=1,n do if v[i]==nil then n=0 break end end
      return (n>0) and "array" or "object"
    end
    local function deepeq(a,b)
      if type(a) ~= type(b) then return false end
      if type(a) ~= "table" then return a == b end
      local ka, kb = kind(a), kind(b)
      if ka ~= kb then return false end
      if ka == "array" then
        if #a ~= #b then return false end
        for i=1,#a do if not deepeq(a[i], b[i]) then return false end end
        return true
      else
        for k,v in pairs(a) do if not deepeq(v, b[k]) then return false end end
        for k,_ in pairs(b) do if a[k]==nil then return false end end
        return true
      end
    end
    local key = KEYS[1]
    local stored = redis.call("GET", key)
    if not stored then return "MISS" end
    local ok1, s = pcall(cjson.decode, stored)
    local ok2, f = pcall(cjson.decode, ARGV[1])
    if not ok1 or not ok2 then return "ERR" end
    return deepeq(s,f) and "OK" or "DIFF"
  '
  local res
  res=$(rc_system EVAL "$lua" 1 "$TRUTH_KEY" "$file_json" 2>/dev/null || true)
  case "$res" in
    OK)   log "truth: VALID (matches ${TRUTH_FILE}) in system-redis"; return 0 ;;
    DIFF) log "truth: INVALID (stored JSON != ${TRUTH_FILE})"; return 2 ;;
    MISS) log "truth: MISSING"; return 1 ;;
    ERR|*) log "truth: INVALID (parse error)"; return 3 ;;
  esac
}

verify_lua() {
  [[ -f "$LUA_FILE" ]] || die "Missing $LUA_FILE"
  local file_sha exists
  file_sha=$(sha1_of_file "$LUA_FILE")
  exists=$(rc_market SCRIPT EXISTS "$file_sha" | awk 'NR==1{print $1}')
  if [[ "$exists" != "1" ]]; then
    log "lua_diff: MISSING in market-redis (expected SHA $file_sha)"
    return 1
  fi
  if rc_market EVALSHA "$file_sha" 0 >/dev/null 2>&1; then
    log "lua_diff: VALID — EVALSHA(sha, 0) executed"
    return 0
  fi
  rc_market SET __ms_old '{"a":1}' >/dev/null
  rc_market SET __ms_new '{"a":2}' >/dev/null
  if rc_market EVALSHA "$file_sha" 2 __ms_old __ms_new __ms_out >/dev/null 2>&1; then
    log "lua_diff: VALID — EVALSHA test executed"
    rc_market DEL __ms_old __ms_new __ms_out >/dev/null
    return 0
  else
    rc_market DEL __ms_old __ms_new __ms_out >/dev/null || true
    log "lua_diff: INVALID"
    return 2
  fi
}

status() {
  log "MarketSwarm bootstrap status:"
  local t=0 l=0
  verify_truth && t=1 || true
  verify_lua   && l=1 || true
  [[ $t -eq 1 && $l -eq 1 ]]
}

init() {
  log "Initializing MarketSwarm truth & Lua..."
  load_truth
  load_lua
  log "Init complete. Verifying..."
  status
}

reset_all() {
  log "RESET: Removing ALL keys in the configured DBs and flushing ALL cached Lua scripts."
  log " - system-redis: ${SYSTEM_REDIS_HOST}:${SYSTEM_REDIS_PORT} db=${SYSTEM_REDIS_DB}"
  log " - market-redis: ${MARKET_REDIS_HOST}:${MARKET_REDIS_PORT} db=${MARKET_REDIS_DB}"
  rc_system SCRIPT FLUSH >/dev/null
  rc_market SCRIPT FLUSH >/dev/null
  rc_system FLUSHDB >/dev/null
  rc_market FLUSHDB >/dev/null
  local sys_dbsize mkt_dbsize sys_script=0 mkt_script=0 lua_sha=""
  sys_dbsize=$(rc_system DBSIZE)
  mkt_dbsize=$(rc_market DBSIZE)
  if [[ -f "$LUA_FILE" ]]; then
    lua_sha=$(sha1_of_file "$LUA_FILE")
    sys_script=$(rc_system SCRIPT EXISTS "$lua_sha" | awk 'NR==1{print $1}')
    mkt_script=$(rc_market SCRIPT EXISTS "$lua_sha" | awk 'NR==1{print $1}')
  fi
  log "RESET verification:"
  log "  system-redis: DBSIZE=${sys_dbsize} script_present=${sys_script}"
  log "  market-redis: DBSIZE=${mkt_dbsize} script_present=${mkt_script}"
  if [[ "$sys_dbsize" == "0" && "$mkt_dbsize" == "0" && "$sys_script" == "0" && "$mkt_script" == "0" ]]; then
    log "RESET verification: OK"
    return 0
  else
    err "RESET verification: FAILED"
    return 1
  fi
}

print_help() {
  cat <<EOF
Usage: $0 {init|load|status|st|reset|clean|purge|help}

Commands:
  init|load   Load truth.json and lua_diff.lua, then verify.
  status|st   Verify truth + lua.
  reset/clean/purge  Remove ALL config from both redis DBs.

Environment:
  All Redis paths, ports, and data files come from ms-busses.env.
EOF
}

case "${1:-help}" in
  init|load)           init ;;
  status|st)           status ;;
  reset|clean|purge)   reset_all ;;
  help|-h|--help)      print_help ;;
  *) die "Unknown command: $1. Use help." ;;
esac