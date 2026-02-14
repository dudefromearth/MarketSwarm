#!/opt/homebrew/bin/bash
set -euo pipefail

###############################################
# MarketSwarm Echo Redis — Cognitive Memory Bus
# Port 6382 | No persistence | volatile-lru
###############################################

BREW_PREFIX="/opt/homebrew"
REDIS_SERVER="$BREW_PREFIX/bin/redis-server"
REDIS_CLI="$BREW_PREFIX/bin/redis-cli"
CONF="$BREW_PREFIX/etc/redis/echo.conf"
PORT=6382

line() { echo "──────────────────────────────────────────────"; }

start_echo() {
  if "$REDIS_CLI" -p $PORT ping &>/dev/null; then
    echo "echo-redis already running on port $PORT"
    return 0
  fi
  echo "Starting echo-redis on port $PORT..."
  "$REDIS_SERVER" "$CONF"
  sleep 0.5
  if "$REDIS_CLI" -p $PORT ping &>/dev/null; then
    echo "echo-redis started"
  else
    echo "Failed to start echo-redis"
    return 1
  fi
}

stop_echo() {
  if "$REDIS_CLI" -p $PORT ping &>/dev/null; then
    echo "Stopping echo-redis..."
    "$REDIS_CLI" -p $PORT shutdown nosave
    echo "echo-redis stopped"
  else
    echo "echo-redis not running"
  fi
}

status_echo() {
  if "$REDIS_CLI" -p $PORT ping &>/dev/null; then
    echo "echo-redis: running (port $PORT)"
    "$REDIS_CLI" -p $PORT INFO memory | grep -E "used_memory_human|maxmemory_human|maxmemory_policy"
    echo "Keys: $("$REDIS_CLI" -p $PORT DBSIZE)"
  else
    echo "echo-redis: not running"
  fi
}

case "${1:-start}" in
  start)   start_echo ;;
  stop)    stop_echo ;;
  restart) stop_echo; sleep 1; start_echo ;;
  status)  status_echo ;;
  *)       echo "Usage: $0 {start|stop|restart|status}"; exit 1 ;;
esac
