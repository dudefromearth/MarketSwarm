#!/bin/sh
set -eu

# --- defaults ---
TRUTH_DB="${TRUTH_DB:-0}"
TRUTH_KEY="${TRUTH_KEY:-truth:doc}"
WAIT_MAX_ATTEMPTS="${WAIT_MAX_ATTEMPTS:-60}"
LUA_PATH="${LUA_PATH:-/seed/lua_diff.lua}"
LUA_KEY="${LUA_KEY:-lua_diff_sha}"
TRUTH_PATH="${TRUTH_PATH:-/seed/truth.json}"

echo "🚀 Bootstrap starting..."

# --- wait for Redis ---
for host in system-redis market-redis; do
  echo "Waiting for ${host}:6379 ..."
  i=0
  until redis-cli -h "$host" -p 6379 PING >/dev/null 2>&1; do
    i=$((i+1))
    if [ "$i" -ge "$WAIT_MAX_ATTEMPTS" ]; then
      echo "⚠️ Timeout waiting for $host — continuing anyway"
      break
    fi
    sleep 0.5
  done
done

# --- seed truth if present ---
for host in system-redis market-redis; do
  if [ -s "$TRUTH_PATH" ]; then
    echo "Seeding truth.json into $host..."
    redis-cli -h "$host" -p 6379 -n "$TRUTH_DB" -x SET "$TRUTH_KEY" < "$TRUTH_PATH" >/dev/null 2>&1 || true
  else
    echo "⚠️ No truth.json found at $TRUTH_PATH — skipping."
  fi
done

# --- load Lua if available ---
if [ -s "$LUA_PATH" ]; then
  echo "Loading Lua diff script into system-redis..."
  SCRIPT_CONTENT=$(cat "$LUA_PATH")
  SHA=$(redis-cli -h system-redis SCRIPT LOAD "$SCRIPT_CONTENT" 2>/dev/null || true)
  if [ -n "$SHA" ]; then
    redis-cli -h system-redis SET "$LUA_KEY" "$SHA" >/dev/null
    echo "✅ Lua script loaded (SHA=$SHA)"
  else
    echo "⚠️ Failed to load Lua script"
  fi
else
  echo "⚠️ No Lua script found at $LUA_PATH — skipping."
fi

# --- sanity check ---
echo "Verifying Lua SHA..."
SHA_FINAL=$(redis-cli -h system-redis GET "$LUA_KEY" 2>/dev/null || true)
if [ -n "$SHA_FINAL" ]; then
  echo "✅ Lua SHA persisted in Redis ($SHA_FINAL)"
else
  echo "⚠️ Lua SHA missing after load (non-fatal)"
fi

echo "🎯 Bootstrap complete."