#!/bin/sh
set -eu

# defaults (no ${…} gymnastics needed here)
TRUTH_DB="${TRUTH_DB:-0}"
TRUTH_KEY="${TRUTH_KEY:-truth:doc}"
WAIT_MAX_ATTEMPTS="${WAIT_MAX_ATTEMPTS:-120}"

# 1) wait for both buses to answer PING
for host in system-redis market-redis; do
  echo "Waiting for ${host}:6379 …"
  i=0
  until redis-cli -h "$host" -p 6379 PING >/dev/null 2>&1; do
    i=$((i+1))
    [ "$i" -ge "$WAIT_MAX_ATTEMPTS" ] && { echo "Timeout waiting for $host"; exit 3; }
    sleep 0.5
  done
done

# 2) seed truth + verify on both buses
for host in system-redis market-redis; do
  echo "Seeding ${host}:6379 …"
  redis-cli -h "$host" -p 6379 -n "$TRUTH_DB" -x SET "$TRUTH_KEY" < /seed/truth.json
  test "$(redis-cli -h "$host" -p 6379 -n "$TRUTH_DB" EXISTS "$TRUTH_KEY")" = "1" \
    || { echo "Seed failed on $host"; exit 2; }
done

echo "Bootstrap OK"