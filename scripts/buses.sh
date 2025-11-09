#!/bin/bash
set -e

BASE_DIR="$HOME/redis"

mkdir -p "$BASE_DIR/system" "$BASE_DIR/market" "$BASE_DIR/rss"

echo "🧠 Starting system-redis (6379)"
redis-server --port 6379 --dir "$BASE_DIR/system" --appendonly yes --daemonize yes

echo "📈 Starting market-redis (6380)"
redis-server --port 6380 --dir "$BASE_DIR/market" --appendonly yes --daemonize yes

echo "📰 Starting rss-redis (6381)"
redis-server --port 6381 --dir "$BASE_DIR/rss" --appendonly yes --daemonize yes

echo "⏳ Waiting for Redis buses..."
for PORT in 6379 6380 6381; do
  until redis-cli -p $PORT ping | grep -q PONG; do
    echo "  → waiting for port $PORT"
    sleep 1
  done
done

echo "✅ All Redis buses running"