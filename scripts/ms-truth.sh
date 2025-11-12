#!/opt/homebrew/bin/bash

# ===== ms-truth.sh: Bootstrap MarketSwarm Truth & Lua Diff =====
# Run from ${MS_ROOT} (~/MarketSwarm). Sources ms-busses.env for paths/ports.
# Commands: init (load truth.json to system, Lua to market), status (check), help (-h/--help).

set -euo pipefail  # Strict mode: exit on error, undefined vars, pipe fails.

# Helper: CLI flags for instance (h p a)
cli_flags() {
    local port="$1"
    local pass="$2"
    echo "-h localhost -p ${port} ${pass:+-a \"${pass}\"}"
}

# Source env (assumes cwd = ${MS_ROOT})
if [[ ! -f ./ms-busses.env ]]; then
    echo "Error: ms-busses.env not found. Run from ${HOME}/MarketSwarm." >&2
    exit 1
fi
source ./ms-busses.env

# Guard: Verify redis-cli
if [[ ! -x "${REDIS_CLI_PATH}" ]]; then
    echo "Error: ${REDIS_CLI_PATH} not found/executable. Install Redis via Brew?" >&2
    exit 1
fi

# Keys
TRUTH_KEY="truth"
LUA_SHA_KEY="lua:diff:sha"

# System & Market flags (with full path)
system_flags=$(cli_flags "${REDIS_SYSTEM_PORT}" "${REDIS_SYSTEM_PASS}")
market_flags=$(cli_flags "${REDIS_MARKET_PORT}" "${REDIS_MARKET_PASS}")

# Helper: Truth status (jq for version)
truth_status() {
    local truth_json=$("${REDIS_CLI_PATH}" $system_flags GET "$TRUTH_KEY" 2>/dev/null || echo "")
    if [[ -n "$truth_json" ]]; then
        local version=$(echo "$truth_json" | jq -r '.version // "unknown"' 2>/dev/null || echo "unknown")
        echo "truth: LOADED (v${version}) in system-redis"
    else
        echo "truth: MISSING in system-redis"
    fi
}

# Helper: Lua status
lua_status() {
    local current_sha=$("${REDIS_CLI_PATH}" $system_flags GET "$LUA_SHA_KEY" 2>/dev/null || echo "")
    if [[ -n "$current_sha" ]]; then
        if "${REDIS_CLI_PATH}" $market_flags SCRIPT EXISTS "$current_sha" >/dev/null; then
            echo "lua_diff: LOADED (SHA ${current_sha}) in market-redis"
        else
            echo "lua_diff: STALE (SHA ${current_sha} missing) in market-redis"
        fi
    else
        echo "lua_diff: UNINSTALLED in market-redis"
    fi
}

# Main: Parse arg
case "${1:-}" in
    init|load)
        echo "Initializing MarketSwarm truth & Lua..."

        # Guard: truth.json
        if [[ ! -f "${TRUTH_JSON_PATH}" ]]; then
            echo "Error: ${TRUTH_JSON_PATH} not found. Ensure file exists." >&2
            exit 1
        fi

        # Load truth.json to system
        if ! "${REDIS_CLI_PATH}" $system_flags EXISTS "$TRUTH_KEY" >/dev/null; then
            truth_content=$(cat "${TRUTH_JSON_PATH}")
            "${REDIS_CLI_PATH}" $system_flags SET "$TRUTH_KEY" "$truth_content"
            echo "Injected truth.json into system-redis."
        else
            echo "Truth already exists in system-redis (skipping)."
        fi

        # Guard: lua_diff.lua
        if [[ ! -f "${LUA_DIFF_PATH}" ]]; then
            echo "Error: ${LUA_DIFF_PATH} not found. Ensure file exists." >&2
            exit 1
        fi

        # Load Lua to market, manage SHA
        current_sha=$("${REDIS_CLI_PATH}" $system_flags GET "$LUA_SHA_KEY" 2>/dev/null || echo "")
        needs_load=true
        if [[ -n "$current_sha" ]] && "${REDIS_CLI_PATH}" $market_flags SCRIPT EXISTS "$current_sha" >/dev/null; then
            echo "Lua diff already loaded in market-redis (SHA ${current_sha}; skipping)."
            needs_load=false
        fi

        if [[ "$needs_load" == true ]]; then
            lua_script=$(cat "${LUA_DIFF_PATH}")
            new_sha=$("${REDIS_CLI_PATH}" $market_flags SCRIPT LOAD "$lua_script")
            "${REDIS_CLI_PATH}" $system_flags SET "$LUA_SHA_KEY" "$new_sha"
            echo "Loaded Lua diff into market-redis (SHA ${new_sha})."
        fi

        echo "Init complete."
        ;;
    status|st)
        echo "MarketSwarm bootstrap status:"
        truth_status
        lua_status
        ;;
    help|-h|--help)
        echo "Usage: $0 {init|status|help}"
        echo "  init/load: Inject truth.json to system-redis, load lua_diff.lua to market-redis"
        echo "  status/st: Check truth key & Lua SHA"
        echo "  help/-h: This message"
        echo ""
        echo "Assumes run from ${MS_ROOT}. Uses ms-busses.env for config."
        exit 0
        ;;
    *)
        echo "Unknown command: $1. See $0 help" >&2
        exit 1
        ;;
esac