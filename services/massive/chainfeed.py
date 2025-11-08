#!/usr/bin/env python3
"""
ChainFeed – Polygon SPX Chain Harvester for Massive
Runs at sub-second cadence (default 0.5 s ≈ 2 Hz).

Responsibilities:
  • Fetch SPX chain via Polygon REST (today → backfill → lookahead)
  • Store JSON snapshot in Redis (SPX:chain:<ts>)
  • Trigger Redis Lua diff atomically
  • Publish lightweight summary to sse:chain-feed
  • Maintain status key and logs
"""

import os
import json
import time
import asyncio
import requests
from datetime import datetime, timezone, timedelta
import redis.asyncio as redis

# ---- Configuration ----
POLYGON_API = "https://api.polygon.io"
API_KEY = os.getenv("POLYGON_API_KEY")
API_SYMBOL = os.getenv("CHAINFEED_API_SYMBOL", "I:SPX")
SYMBOL = os.getenv("CHAINFEED_SYMBOL", "SPX")

REDIS_HOST = os.getenv("REDIS_HOST", "system-redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
INTERVAL_SEC = float(os.getenv("CHAINFEED_INTERVAL", "0.5"))  # 2 Hz default

EXPIRY_BACK_DAYS = int(os.getenv("EXPIRY_BACK_DAYS", "7"))
EXPIRY_FWD_DAYS = int(os.getenv("EXPIRY_FWD_DAYS", "3"))
PREFER_BACKFILL = os.getenv("PREFER_BACKFILL", "1") == "1"

CHANNEL = "sse:chain-feed"  # publish endpoint


# ---- Helpers ----
def _poly_json(url: str, params: dict) -> dict | None:
    try:
        r = requests.get(url, params=params, timeout=8)
        if not r.ok:
            print(f"[Polygon] HTTP {r.status_code} for {url}")
            return None
        return r.json()
    except Exception as e:
        print(f"[Polygon] request error: {e}")
        return None


def _fetch_chain_for_date(api_symbol: str, api_key: str, ymd: str):
    """Fetch full option chain for a specific expiration date."""
    url = f"{POLYGON_API}/v3/snapshot/options/{api_symbol}?expiration_date={ymd}&limit=250&include_greeks=true&apiKey={api_key}"
    out = []
    while url:
        j = _poly_json(url, {})
        if not j:
            break
        out.extend(j.get("results", []))
        url = j.get("next_url")
        if url:
            join = "&" if "?" in url else "?"
            url = f"{url}{join}include_greeks=true&apiKey={api_key}"
    return out


def _ymd(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def fetch_best_chain_and_expiration(api_symbol: str, api_key: str):
    """Try today’s expiry first, then backfill or lookahead."""
    now_utc = datetime.now(timezone.utc)
    today = _ymd(now_utc)

    # 1️⃣ today
    chain = _fetch_chain_for_date(api_symbol, api_key, today)
    if chain:
        return chain, today, "today"

    # 2️⃣ fallback search
    back_days = range(1, EXPIRY_BACK_DAYS + 1)
    fwd_days = range(1, EXPIRY_FWD_DAYS + 1)

    def try_back():
        for d in back_days:
            ymd = _ymd(now_utc - timedelta(days=d))
            c = _fetch_chain_for_date(api_symbol, api_key, ymd)
            if c:
                return c, ymd, "backfill"
        return [], "", ""

    def try_fwd():
        for d in fwd_days:
            ymd = _ymd(now_utc + timedelta(days=d))
            c = _fetch_chain_for_date(api_symbol, api_key, ymd)
            if c:
                return c, ymd, "lookahead"
        return [], "", ""

    if PREFER_BACKFILL:
        c, ymd, mode = try_back()
        if c:
            return c, ymd, mode
        return try_fwd()
    else:
        c, ymd, mode = try_fwd()
        if c:
            return c, ymd, mode
        return try_back()


# ---- Store, Diff, and Publish ----
async def store_and_diff(r: redis.Redis, chain, symbol: str, exp_ymd: str, mode: str):
    """Store snapshot, trigger Lua diff, publish summary, update status."""
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    key = f"{symbol}:chain:{ts}"
    payload = json.dumps({
        "symbol": symbol,
        "expiration": exp_ymd,
        "mode": mode,
        "count": len(chain),
        "contracts": chain,
    }, default=str)

    # Store snapshot
    await r.set(key, payload)
    await r.set(f"{symbol}:latest_full", key)

    # Run Lua diff atomically
    sha = await r.get("lua_diff_sha")
    if sha:
        prev_key = await r.get(f"{symbol}:prev_full")
        if prev_key:
            try:
                await r.evalsha(sha, 2, prev_key, key, f"{symbol}:latest_diff")
            except Exception as e:
                print(f"[ChainFeed Lua Diff Error] {e}")
        await r.set(f"{symbol}:prev_full", key)
    else:
        print("⚠️ No Lua diff script registered in Redis.")

    # Publish summary
    summary = {
        "symbol": symbol,
        "expiration": exp_ymd,
        "mode": mode,
        "count": len(chain),
        "timestamp": ts,
    }
    await r.publish(CHANNEL, json.dumps(summary))
    print(f"📡 Published {symbol} {exp_ymd} ({mode}) count={len(chain)} to {CHANNEL}")

    # Update status
    await r.hset(
        "massive:chainfeed:status",
        mapping={
            "last_run_ts": time.time(),
            "last_status": "success",
            "expiration": exp_ymd,
            "mode": mode,
            "contracts": len(chain),
        },
    )


# ---- Main Worker ----
async def run_chainfeed():
    if not API_KEY:
        raise RuntimeError("Missing POLYGON_API_KEY environment variable")

    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    print(f"🚀 ChainFeed starting for {SYMBOL} ({API_SYMBOL}) interval={INTERVAL_SEC}s")

    # --- wait for bootstrap / Lua script ---
    for _ in range(40):  # up to 20 s
        sha = await r.get("lua_diff_sha")
        if sha:
            print(f"✅ Lua diff script detected (SHA={sha}) — proceeding.")
            break
        print("⏳ Waiting for bootstrap to load lua_diff_sha …")
        await asyncio.sleep(0.5)
    else:
        print("⚠️ Lua diff script not found after 20s, continuing anyway (diffs disabled).")

    # --- main loop ---
    while True:
        try:
            chain, exp, mode = fetch_best_chain_and_expiration(API_SYMBOL, API_KEY)
            if chain:
                await store_and_diff(r, chain, SYMBOL, exp, mode)
            else:
                print("⚠️ No chain data available from Polygon.")
        except Exception as e:
            await r.hset(
                "massive:chainfeed:status",
                mapping={"last_run_ts": time.time(), "last_status": f"failed: {e}"},
            )
            print(f"[ChainFeed Error] {e}")

        await asyncio.sleep(INTERVAL_SEC)


if __name__ == "__main__":
    asyncio.run(run_chainfeed())