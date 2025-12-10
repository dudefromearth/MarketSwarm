#!/usr/bin/env bash
set -euo pipefail

# tail_massive_trades.sh
#
# Usage:
#   ./tail_massive_trades.sh SPX 20251208
#
# Env (optional):
#   REDIS_URL   - redis connection (default: redis://127.0.0.1:6380)

REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6380}"

UNDERLYING="${1:-SPX}"
EXPIRY_YYYYMMDD="${2:-20251208}"

STREAM_KEY="massive:trades:${UNDERLYING}:${EXPIRY_YYYYMMDD}"

# Start from the "end" ($) so we only see *new* messages as they arrive.
START_ID="${3:-$}"

echo "──────────────────────────────────────────────"
echo " Tailing Massive trades stream"
echo "  Redis URL : ${REDIS_URL}"
echo "  Underlying: ${UNDERLYING}"
echo "  Expiry    : ${EXPIRY_YYYYMMDD}"
echo "  Stream    : ${STREAM_KEY}"
echo "  Start ID  : ${START_ID}"
echo "  Command   : XREAD BLOCK 0 STREAMS ${STREAM_KEY} ${START_ID}"
echo " Ctrl+C to exit."
echo "──────────────────────────────────────────────"
echo

exec redis-cli -u "${REDIS_URL}" \
  XREAD BLOCK 0 STREAMS "${STREAM_KEY}" "${START_ID}"