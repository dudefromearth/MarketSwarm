#!/usr/bin/env python3
"""
MASSIVE chainfeed_worker.py
------------------------------------
Thin wrapper around Conor's DTE worker logic.

Differences vs original:
  • Only runs ONE sweep (run_once)
  • Publishes a MASSIVE-normalized message into MARKET_REDIS:
        key = "sse:chain-feed"
        type = "chainfeed"
        payload = {
            "ts": ts,
            "symbol": "SPX",
            "count": <N contracts>,
            "spot": <spot>,
            "expirations": [...],
            ...
        }
  • No pubsub, no trails, no TTL mgmt — Conor’s worker handles raw Redis work.
  • Orchestrator controls cadence (default: every 2 seconds)
"""

import json
from datetime import datetime, timezone

# Import Conor’s full DTE worker (as a module)
# We only use run_once(), which returns delta_count.
import dte_feed_worker as run_once


# ---------------------------------------------------------------------------
# Small helper for Redis publishing
# ---------------------------------------------------------------------------
def _publish_chainfeed(r_market, payload: dict):
    """
    Publish to market-redis SSE bus as specified in truth.json:
        key = "sse:chain-feed"
    """
    key = "sse:chain-feed"
    r_market.xadd(key, {"json": json.dumps(payload)})
    return key


# ---------------------------------------------------------------------------
# MASSIVE wrapper
# ---------------------------------------------------------------------------
def run_once(r_market=None):
    """
    Executes ONE sweep of the SPX option chain (multi-DTE),
    then publishes a summary event to MARKET_REDIS key: sse:chain-feed.

    The heavy lifting (Polygon fetch, greeks, diffs, multi-expiry)
    is done inside dte_feed_worker.run_once().
    """

    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

    try:
        # Conor's worker prints everything internally.
        delta = dte.run_once()      # <-- does all the heavy work

        # Massive-standard chainfeed envelope
        payload = {
            "type": "chainfeed",
            "symbol": dte.SYMBOL,
            "ts": ts,
            "delta": int(delta),
            "source": "massive/chainfeed_worker",
        }

        if r_market is not None:
            _publish_chainfeed(r_market, payload)

        print(f"[chainfeed_worker] Published → sse:chain-feed  Δ={delta}")

    except Exception as e:
        print(f"[chainfeed_worker] ERROR: {e}")
        raise