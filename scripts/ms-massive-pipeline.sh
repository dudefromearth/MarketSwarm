#!/usr/bin/env bash
set -euo pipefail

###############################################
# MarketSwarm – ms-massive-debug.sh
# Component-by-component Massive pipeline debug
#
# No orchestrator. You call each worker explicitly:
#
#   ms-massive-debug.sh spot-tick
#   ms-massive-debug.sh chain-tick
#   ms-massive-debug.sh diag
#   ms-massive-debug.sh ws-test
###############################################

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_ROOT="$ROOT/services/massive"
VENV="$ROOT/.venv"
VENV_PY="$VENV/bin/python"

###############################################
# EDITABLE CONFIG (known-good defaults)
###############################################

MASSIVE_SYMBOL="I:SPX"
MASSIVE_UNDERLYING="SPX"
MASSIVE_API_KEY="pdjraOWSpDbg3ER_RslZYe3dmn4Y7WCC"

SYSTEM_REDIS_URL="redis://127.0.0.1:6379"
MARKET_REDIS_URL="redis://127.0.0.1:6380"
INTEL_REDIS_URL="redis://127.0.0.1:6381"

MASSIVE_WS_URL="wss://socket.massive.com/options"
MASSIVE_WS_STRIKE_STEP=5
MASSIVE_WS_EXPIRY_YYYYMMDD=""   # "" => auto-today for ws-test

MASSIVE_CHAIN_INTERVAL_SEC=60
MASSIVE_CHAIN_STRIKE_RANGE=150
MASSIVE_CHAIN_NUM_EXPIRATIONS=5
MASSIVE_CHAIN_SNAPSHOT_TTL_SEC=600
MASSIVE_CHAIN_TRAIL_WINDOW_SEC=86400
MASSIVE_CHAIN_TRAIL_TTL_SEC=172800

MASSIVE_SPOT_INTERVAL_SEC=1
MASSIVE_SPOT_TRAIL_WINDOW_SEC=86400
MASSIVE_SPOT_TRAIL_TTL_SEC=172800

DEBUG_MASSIVE="true"
SERVICE_ID="massive"

###############################################
# Usage
###############################################

usage() {
  cat <<EOF
Usage:
  $(basename "$0") spot-tick    # run one SpotWorker tick
  $(basename "$0") chain-tick   # run one ChainWorker cycle
  $(basename "$0") diag         # inspect Redis (spot, chain, ws params)
  $(basename "$0") ws-test      # run WsWorker briefly (needs ws params)
  $(basename "$0") -h|--help    # show this help

Config is edited at the top of this file (no external env required).

Key defaults:
  MASSIVE_SYMBOL       = $MASSIVE_SYMBOL
  MASSIVE_UNDERLYING   = $MASSIVE_UNDERLYING
  MARKET_REDIS_URL     = $MARKET_REDIS_URL
  MASSIVE_WS_URL       = $MASSIVE_WS_URL
  MASSIVE_WS_STRIKE_STEP = $MASSIVE_WS_STRIKE_STEP
EOF
}

if [[ $# -lt 1 ]]; then
  usage
  exit 1
fi

CMD="$1"; shift || true

###############################################
# Export config into env for Python
###############################################

export MASSIVE_SYMBOL
export MASSIVE_UNDERLYING
export MASSIVE_API_KEY

export SYSTEM_REDIS_URL
export MARKET_REDIS_URL
export INTEL_REDIS_URL

export MASSIVE_WS_URL
export MASSIVE_WS_STRIKE_STEP
export MASSIVE_WS_EXPIRY_YYYYMMDD

export MASSIVE_CHAIN_INTERVAL_SEC
export MASSIVE_CHAIN_STRIKE_RANGE
export MASSIVE_CHAIN_NUM_EXPIRATIONS
export MASSIVE_CHAIN_SNAPSHOT_TTL_SEC
export MASSIVE_CHAIN_TRAIL_WINDOW_SEC
export MASSIVE_CHAIN_TRAIL_TTL_SEC

export MASSIVE_SPOT_INTERVAL_SEC
export MASSIVE_SPOT_TRAIL_WINDOW_SEC
export MASSIVE_SPOT_TRAIL_TTL_SEC

export DEBUG_MASSIVE
export SERVICE_ID

cd "$ROOT"

###############################################
# Commands
###############################################

case "$CMD" in
  -h|--help|help)
    usage
    ;;

  spot-tick)
    echo "▶ SpotWorker one tick…"
    "$VENV_PY" - <<'PYCODE'
import asyncio, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SERVICE_ROOT = ROOT / "services" / "massive"
sys.path.insert(0, str(SERVICE_ROOT))

from intel.spot_worker import SpotWorker
import logutil

async def main():
    cfg = {
        "service_name": "massive",
        "env": dict(os.environ),
    }
    w = SpotWorker(cfg)
    await w._tick_once()  # one tick only
    logutil.log("massive", "INFO", "✅", "SpotWorker tick completed")

asyncio.run(main())
PYCODE
    ;;

  chain-tick)
    echo "▶ ChainWorker one cycle…"
    "$VENV_PY" - <<'PYCODE'
import asyncio, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SERVICE_ROOT = ROOT / "services" / "massive"
sys.path.insert(0, str(SERVICE_ROOT))

from intel.chain_worker import ChainWorker
import logutil

async def main():
    cfg = {
        "service_name": "massive",
    }
    w = ChainWorker(cfg)
    await w._run_once()  # one cycle only
    logutil.log("massive", "INFO", "✅", "ChainWorker cycle completed")

asyncio.run(main())
PYCODE
    ;;

  diag)
    echo "▶ Diagnostic: spot, chain, ws params…"
    "$VENV_PY" - <<'PYCODE'
import asyncio, os
from redis.asyncio import Redis
from datetime import datetime

async def main():
    market_url = os.getenv("MARKET_REDIS_URL", "redis://127.0.0.1:6380")
    r = Redis.from_url(market_url, decode_responses=True)
    underlying = os.getenv("MASSIVE_UNDERLYING", "SPX")

    print(f"Market Redis URL: {market_url}")
    print(f"Underlying: {underlying}")
    print("---- Spot ----")
    for sym in (underlying, "VIX"):
        key = f"massive:model:spot:{sym}"
        val = await r.get(key)
        print(f"{key} = {val[:120] + '…' if val and len(val) > 120 else val}")

    print("---- Chain latest pointers (first few) ----")
    # list some CHAIN:SPX:EXP:*:latest keys
    keys = sorted(await r.keys(f"CHAIN:{underlying}:EXP:*:latest"))[:5]
    if not keys:
        print("(no CHAIN latest keys found)")
    else:
        for k in keys:
            v = await r.get(k)
            print(f"{k} -> {v}")

    print("---- WS params key ----")
    expiry = os.getenv("MASSIVE_WS_EXPIRY_YYYYMMDD", "").strip()
    if not expiry:
        expiry = datetime.utcnow().strftime("%Y%m%d")
    params_key = f"massive:ws:params:{expiry}"
    params = await r.get(params_key)
    print(f"{params_key} = {('<set, length=' + str(len(params.split(','))) + ' channels>') if params else '<<MISSING>>'}")

    await r.close()

asyncio.run(main())
PYCODE
    ;;

  ws-test)
    echo "▶ WsWorker test run…"
    "$VENV_PY" - <<'PYCODE'
import asyncio, os, sys
from pathlib import Path
from datetime import datetime

from redis.asyncio import Redis

ROOT = Path(__file__).resolve().parent
SERVICE_ROOT = ROOT / "services" / "massive"
sys.path.insert(0, str(SERVICE_ROOT))

from intel.ws_worker import WsWorker
import logutil

async def main():
    # Resolve expiry
    expiry = os.getenv("MASSIVE_WS_EXPIRY_YYYYMMDD", "").strip()
    if not expiry:
        expiry = datetime.utcnow().strftime("%Y%m%d")
        os.environ["MASSIVE_WS_EXPIRY_YYYYMMDD"] = expiry

    market_url = os.getenv("MARKET_REDIS_URL", "redis://127.0.0.1:6380")
    shared_redis = Redis.from_url(market_url, decode_responses=True)

    cfg = {
        "service_name": "massive",
        "api_symbol": os.getenv("MASSIVE_SYMBOL", "I:SPX"),
        "ws_url": os.getenv("MASSIVE_WS_URL", "wss://socket.massive.com/options"),
        "ws_expiry_yyyymmdd": expiry,
        "ws_reconnect_delay_sec": 5.0,
        "market_redis_url": market_url,
    }

    w = WsWorker(cfg, shared_redis=shared_redis)
    stop_event = asyncio.Event()

    logutil.log("massive", "INFO", "🧪", f"WsWorker test run for expiry={expiry}")

    try:
        # Try a single connect-and-stream with timeout
        await asyncio.wait_for(w._connect_and_stream(stop_event), timeout=30.0)
    except asyncio.TimeoutError:
        logutil.log("massive", "INFO", "⏱️", "WsWorker test timed out after 30s (expected in debug)")
    finally:
        stop_event.set()
        await shared_redis.close()
        logutil.log("massive", "INFO", "✅", "WsWorker test finished")

asyncio.run(main())
PYCODE
    ;;

  *)
    echo "ERROR: Unknown command '$CMD'" >&2
    echo >&2
    usage
    exit 1
    ;;
esac