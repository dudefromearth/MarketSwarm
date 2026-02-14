#!/opt/homebrew/bin/bash
set -euo pipefail

###############################################
# MarketSwarm Vexy Hydrator – Launcher
###############################################

export SYSTEM_REDIS_URL="redis://127.0.0.1:6379"
export MARKET_REDIS_URL="redis://127.0.0.1:6380"
export ECHO_REDIS_URL="redis://127.0.0.1:6382"
export HYDRATOR_PORT="${HYDRATOR_PORT:-3007}"

BREW_REDIS="/opt/homebrew/bin/redis-cli"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE="vexy_hydrator"
MAIN="$ROOT/services/vexy_hydrator/main.py"

VENV="$ROOT/.venv"
VENV_PY="$VENV/bin/python"

line() { echo "──────────────────────────────────────────────"; }

line
echo " MarketSwarm – Vexy Hydrator"
line
echo "ROOT: $ROOT"
echo "PORT: $HYDRATOR_PORT"
echo ""

# Validate tools
for cmd in "$VENV_PY" "$BREW_REDIS"; do
  [[ -x "$cmd" ]] && echo "Found $cmd" || { echo "Missing $cmd"; exit 1; }
done

# Validate truth
HAS_TRUTH=$($BREW_REDIS -h 127.0.0.1 -p 6379 EXISTS truth)
[[ "$HAS_TRUTH" -eq 1 ]] && echo "Truth found" || { echo "Missing truth"; exit 1; }

# Validate echo-redis
$BREW_REDIS -h 127.0.0.1 -p 6382 PING &>/dev/null && echo "Echo-redis running" || {
  echo "Echo-redis not running on port 6382 — starting..."
  "$ROOT/scripts/ms-echo-redis.sh" start
}

line
echo "Launching Vexy Hydrator"
line

export SERVICE_ID="$SERVICE"
exec "$VENV_PY" "$MAIN"
