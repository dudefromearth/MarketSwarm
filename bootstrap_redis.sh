for port in "$SYS_PORT" "$MKT_PORT"; do
  redis-cli -h 127.0.0.1 -p "$port" get truth:doc >/dev/null 2>&1 \
    && echo "✅ Redis on port $port has truth:doc" \
    || echo "⚠️ Missing truth:doc on port $port"
done

echo ""#!/usr/bin/env bash
# MarketSwarm Bootstrap — SAFE SYSTEM INITIALIZATION
# -------------------------------------------------------
# 1. Removes existing Redis containers and volumes (with warning)
# 2. Starts clean system + market Redis
# 3. Ensures both are attached to the shared network (default: marketswarm-bus)
# 4. Loads truth.json and initializes endpoints
# -------------------------------------------------------

set -euo pipefail

echo "🧠 MarketSwarm Bootstrap — SAFE SYSTEM INITIALIZATION"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRUTH_FILE="$ROOT/truth.json"
SYS_PORT=6379
MKT_PORT=6380
# 🔗 Shared network name used by docker-compose.yml (external: marketswarm-bus)
NET_NAME=${NET_NAME:-marketswarm-bus}

# --- Sanity checks ---
[ -f "$TRUTH_FILE" ] || { echo "❌ Missing truth.json in $ROOT"; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "❌ Docker not installed"; exit 1; }
command -v redis-cli >/dev/null 2>&1 || { echo "❌ redis-cli not installed"; exit 1; }

echo ""
echo "⚠️  WARNING: This operation will remove and recreate all Redis containers and volumes."
echo "   This means:"
echo "     • Any existing Redis data will be permanently deleted."
echo "     • New clean system-redis and market-redis instances will be created."
echo ""
read -p "Proceed with full system bootstrap? (yes/[no]): " CONFIRM
[[ ${CONFIRM:-no} == yes ]] || { echo "🚫 Aborted by user."; exit 0; }

echo ""
echo "🧹 Cleaning up existing Redis containers and volumes..."
for name in marketswarm-system-redis-1 marketswarm-market-redis-1 system-redis market-redis; do
  docker stop "$name" >/dev/null 2>&1 || true
  docker rm "$name" >/dev/null 2>&1 || true
done
for vol in $(docker volume ls -q | grep redis || true); do
  docker volume rm "$vol" >/dev/null 2>&1 || true
done
sleep 2
echo "✅ Old Redis containers and volumes removed."

# --- Ensure shared network exists before starting containers ---
docker network create "$NET_NAME" 2>/dev/null || true

# --- Step 1: Start clean Redis containers ---
echo "⚙️  Starting clean Redis buses..."
# NOTE: We keep host reachability on 127.0.0.1 while attaching to the shared Docker network.
#       system-redis exposes 6379→6379; market-redis exposes 6380→6379 inside the container.
docker run -d \
  --name system-redis \
  --network "$NET_NAME" \
  --network-alias system-redis \
  --restart unless-stopped \
  -p 127.0.0.1:${SYS_PORT}:${SYS_PORT} \
  -v system_redis_data:/data \
  redis:7-alpine >/dev/null

docker run -d \
  --name market-redis \
  --network "$NET_NAME" \
  --network-alias market-redis \
  --restart unless-stopped \
  -p 127.0.0.1:${MKT_PORT}:6379 \
  -v market_redis_data:/data \
  redis:7-alpine >/dev/null
sleep 3

# --- Step 2: Verify Redis health ---
echo "🔍 Checking Redis availability..."
for name in system market; do
  port=$([[ "$name" == "system" ]] && echo "$SYS_PORT" || echo "$MKT_PORT")
  if redis-cli -h 127.0.0.1 -p "$port" ping >/dev/null 2>&1; then
    echo "✅ $name-redis is up and responding on port $port."
  else
    echo "❌ $name-redis not responding on port $port"
    exit 1
  fi
done

# --- Step 3: Attach Redis to the shared network ---
echo "🔗 Ensuring Redis containers are connected to the $NET_NAME network..."
# Create the shared network if missing (matches docker-compose external network)
docker network create "$NET_NAME" 2>/dev/null || true

for container in system-redis market-redis; do
  if docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
    if ! docker network inspect "$NET_NAME" --format '{{json .Containers}}' | grep -q "$container"; then
      docker network connect "$NET_NAME" "$container" >/dev/null 2>&1 || true
      echo "   → Attached $container to $NET_NAME"
    else
      echo "   → $container already attached to $NET_NAME"
    fi
  else
    echo "   ⚠️  $container not found; cannot attach to network"
  fi
done

echo "✅ Redis containers connected to $NET_NAME network."

# --- Step 4: Load truth into Redis ---
echo "📜 Loading truth.json into Redis buses..."
python3 - <<'PYCODE'
import redis, json, sys, os

TRUTH_FILE = os.path.join(os.getcwd(), "truth.json")
print(f"[Bootstrap] Loading Truth from {TRUTH_FILE}")

try:
    with open(TRUTH_FILE, "r") as f:
        truth = json.load(f)
except Exception as e:
    print(f"❌ Could not parse truth.json: {e}")
    sys.exit(1)

for bus, port in {"system": 6379, "market": 6380}.items():
    try:
        r = redis.Redis(host="127.0.0.1", port=port, decode_responses=True)
        r.set("truth:doc", json.dumps(truth))
        r.set("truth:version", truth.get("version", "1.0"))
        r.set("truth:ts", truth.get("timestamp", "unknown"))
        print(f"✅ truth.json loaded into {bus}-redis")
    except Exception as e:
        print(f"❌ Failed to load truth into {bus}-redis: {e}")
PYCODE

# --- Step 5: Verify truth presence ---
echo ""
echo "🧩 Verifying Truth Presence..."
for port in "$SYS_PORT" "$MKT_PORT"; do
  redis-cli -h 127.0.0.1 -p "$port" get truth:doc >/dev/null 2>&1 \
    && echo "✅ Redis on port $port has truth:doc" \
    || echo "⚠️ Missing truth:doc on port $port"
done
echo ""

# --- Final summary ---
echo ""
echo "🚀 MarketSwarm Bootstrap Complete"
echo "----------------------------------"
echo "System Redis  → redis://127.0.0.1:$SYS_PORT"
echo "Market Redis  → redis://127.0.0.1:$MKT_PORT"
echo "Truth Source  → $TRUTH_FILE"
echo "Network       → $NET_NAME (Redis containers attached)"
echo "----------------------------------"
echo "🩺 Ready for container spin-up."
