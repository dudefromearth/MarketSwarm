#!/opt/homebrew/bin/bash

# ===== ms-busses.sh: Manage MarketSwarm Redis Instances =====
# Run from ${MS_ROOT} (~/MarketSwarm). Sources ms-busses.env for paths/ports.
# Commands: up (start all), down (stop all), status (check all), help (-h/--help).

set -euo pipefail  # Strict mode: exit on error, undefined vars, pipe fails.

# Source env (assumes cwd = ${MS_ROOT})
if [[ ! -f ./ms-busses.env ]]; then
    echo "Error: ms-busses.env not found. Run from ${HOME}/MarketSwarm." >&2
    exit 1
fi
source ./ms-busses.env

# Derived paths (per-instance isolation under MS_ROOT)
REDIS_BASE_DIR="${MS_ROOT}/redis"
REDIS_SYSTEM_DIR="${REDIS_BASE_DIR}/system"
REDIS_MARKET_DIR="${REDIS_BASE_DIR}/market"
REDIS_INTEL_DIR="${REDIS_BASE_DIR}/intel"
LOGS_DIR="${MS_ROOT}/logs"

# Echo Redis uses a dedicated config file (no persistence, volatile-lru)
ECHO_CONF="${BREW_PREFIX}/etc/redis/echo.conf"

# Instance map: array of [name, port|pass|dir] (pipe delim for empty-pass safety)
declare -A INSTANCES=(
    [system]="${REDIS_SYSTEM_PORT}|${REDIS_SYSTEM_PASS}|${REDIS_SYSTEM_DIR}"
    [market]="${REDIS_MARKET_PORT}|${REDIS_MARKET_PASS}|${REDIS_MARKET_DIR}"
    [intel]="${REDIS_INTEL_PORT}|${REDIS_INTEL_PASS}|${REDIS_INTEL_DIR}"
)

# Helper: CLI flags for instance (h p a)
cli_flags() {
    local port="$1"
    local pass="$2"
    echo "-h localhost -p ${port} ${pass:+-a \"${pass}\"}"
}

# Helper: Ensure dir exists, mkdir -p
ensure_dir() {
    local dir="$1"
    if [[ -z "$dir" ]]; then
        echo "Error: Empty directory path." >&2
        exit 1
    fi
    mkdir -p "$dir"
    mkdir -p "${dir}/data"  # Subdir for dump.rdb
}

# Helper: Check if port running (ping)
is_port_running() {
    local port="$1"
    local pass="$2"
    local flags
    flags=$(cli_flags "$port" "$pass")
    "${REDIS_CLI_PATH}" $flags ping >/dev/null 2>&1
}

# Helper: Start single instance
start_instance() {
    local name="$1"
    local port="$2"
    local pass="$3"
    local dir="$4"
    local pidfile="${dir}/redis.pid"
    local logfile="${LOGS_DIR}/redis-${name}.log"
    local dbfilename="dump-${name}.rdb"

    ensure_dir "$dir"
    ensure_dir "$LOGS_DIR"

    if is_port_running "$port" "$pass"; then
        echo "Instance ${name} (port ${port}) already running." >&2
        return 0
    fi

    if [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
        echo "Instance ${name} (port ${port}) already running (PID $(cat "$pidfile"))." >&2
        return 0
    fi

    echo "Starting ${name} on port ${port}..."
    nohup "${REDIS_SERVER_PATH}" \
        --bind 127.0.0.1 \
        --port "${port}" \
        --dir "${dir}/data" \
        --pidfile "${pidfile}" \
        --logfile "${logfile}" \
        --dbfilename "${dbfilename}" \
        ${pass:+--requirepass "${pass}"} \
        --daemonize yes \
        --supervised systemd \
        --timeout 0 \
        --tcp-keepalive 300 \
        --save 900 1 \
        --save 300 10 \
        --save 60 10000 \
        >> "${logfile}" 2>&1 &

    # Wait for startup (poll pidfile + ping)
    for i in {1..30}; do
        if [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null && is_port_running "$port" "$pass"; then
            echo "Instance ${name} started (PID $(cat "$pidfile"))."
            return 0
        fi
        sleep 1
    done
    echo "Error: Failed to start ${name}." >&2
    exit 1
}

# Helper: Stop single instance
stop_instance() {
    local name="$1"
    local port="$2"
    local pass="$3"
    local dir="$4"
    local pidfile="${dir}/redis.pid"
    local flags
    flags=$(cli_flags "$port" "$pass")

    if ! is_port_running "$port" "$pass"; then
        echo "Instance ${name} (port ${port}) not running."
        return 0
    fi

    echo "Stopping ${name} on port ${port}..."
    if "${REDIS_CLI_PATH}" $flags shutdown nosave >/dev/null 2>&1; then
        echo "Instance ${name} shut down gracefully."
        rm -f "$pidfile"
    else
        # Fallback: kill if pidfile
        if [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
            kill "$(cat "$pidfile")"
            echo "Instance ${name} killed (CLI shutdown failed)."
            rm -f "$pidfile"
        else
            echo "Instance ${name} shutdown failed (no PID; manual kill needed)." >&2
        fi
    fi
}

# Helper: Status single instance
status_instance() {
    local name="$1"
    local port="$2"
    local pass="$3"
    local dir="$4"
    local pidfile="${dir}/redis.pid"
    local flags
    flags=$(cli_flags "$port" "$pass")
    local pid_info=""
    local status="ERROR"

    if [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
        pid_info="PID $(cat "$pidfile")"
    fi

    if is_port_running "$port" "$pass"; then
        status=$("${REDIS_CLI_PATH}" $flags ping 2>/dev/null || echo "ERROR")
        echo "${name}: RUNNING (${pid_info:-PID unknown}, Port ${port}) - Ping: ${status}"
    else
        echo "${name}: STOPPED (Port ${port})"
    fi
}

# ===== Echo Redis (config-file-driven, no persistence, volatile-lru) =====

start_echo() {
    if "${REDIS_CLI_PATH}" -p "${REDIS_ECHO_PORT}" ping &>/dev/null; then
        echo "Instance echo (port ${REDIS_ECHO_PORT}) already running."
        return 0
    fi
    if [[ ! -f "$ECHO_CONF" ]]; then
        echo "Error: Echo config not found: ${ECHO_CONF}" >&2
        return 1
    fi
    echo "Starting echo on port ${REDIS_ECHO_PORT}..."
    "${REDIS_SERVER_PATH}" "${ECHO_CONF}"
    sleep 0.5
    if "${REDIS_CLI_PATH}" -p "${REDIS_ECHO_PORT}" ping &>/dev/null; then
        echo "Instance echo started."
    else
        echo "Error: Failed to start echo." >&2
        return 1
    fi
}

stop_echo() {
    if ! "${REDIS_CLI_PATH}" -p "${REDIS_ECHO_PORT}" ping &>/dev/null; then
        echo "Instance echo (port ${REDIS_ECHO_PORT}) not running."
        return 0
    fi
    echo "Stopping echo on port ${REDIS_ECHO_PORT}..."
    "${REDIS_CLI_PATH}" -p "${REDIS_ECHO_PORT}" shutdown nosave
    echo "Instance echo shut down gracefully."
}

status_echo() {
    if "${REDIS_CLI_PATH}" -p "${REDIS_ECHO_PORT}" ping &>/dev/null; then
        echo "echo: RUNNING (Port ${REDIS_ECHO_PORT}) - Ping: PONG"
    else
        echo "echo: STOPPED (Port ${REDIS_ECHO_PORT})"
    fi
}

# Main: Parse arg
case "${1:-}" in
    up|start)
        echo "Bringing up all Redis instances..."
        for name in "${!INSTANCES[@]}"; do
            IFS='|' read -r port pass dir <<< "${INSTANCES[$name]}"
            start_instance "$name" "$port" "$pass" "$dir"
        done
        start_echo
        echo "All instances up."
        ;;
    down|stop)
        echo "Bringing down all Redis instances..."
        for name in "${!INSTANCES[@]}"; do
            IFS='|' read -r port pass dir <<< "${INSTANCES[$name]}"
            stop_instance "$name" "$port" "$pass" "$dir"
        done
        stop_echo
        echo "All instances down."
        ;;
    status|st)
        echo "Redis instances status:"
        for name in "${!INSTANCES[@]}"; do
            IFS='|' read -r port pass dir <<< "${INSTANCES[$name]}"
            status_instance "$name" "$port" "$pass" "$dir"
        done
        status_echo
        ;;
    help|-h|--help)
        echo "Usage: $0 {up|down|status|help}"
        echo "  up/start: Start all instances"
        echo "  down/stop: Stop all instances"
        echo "  status/st: Check status"
        echo "  help/-h: This message"
        echo ""
        echo "Assumes run from ${MS_ROOT}. Uses ms-busses.env for config."
        echo "Logs to ${LOGS_DIR}/redis-*.log"
        exit 0
        ;;
    *)
        echo "Unknown command: $1. See $0 help" >&2
        exit 1
        ;;
esac