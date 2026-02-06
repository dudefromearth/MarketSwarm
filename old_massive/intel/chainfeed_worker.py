#!/usr/bin/env python3
"""
chainfeed_worker.py — Pull a trimmed options chain snapshot from Massive
and publish it into market-redis for downstream services (SSE, Vigil, Vexy).

This is a prototype “pull” loop: it fetches a limited snapshot on a cadence,
stores the latest chain in a redis key, and emits a stream event on
`sse:chain-feed` so listeners can react immediately.
"""
import json
import os
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import redis
import requests


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def _redis_from_url(url: str) -> redis.Redis:
    parsed = urllib.parse.urlparse(url)
    return redis.Redis(
        host=parsed.hostname or "127.0.0.1",
        port=parsed.port or 6379,
        decode_responses=True,
    )


def _build_options_url(base_url: str, symbol: str) -> str:
    base = base_url.rstrip("/")
    encoded = urllib.parse.quote(symbol)
    return f"{base}/{encoded}"


def _fetch_chain(
    symbol: str,
    api_key: str,
    base_url: str,
    limit: int = 250,
) -> List[Dict[str, Any]]:
    params = {
        "limit": limit,
        "order": "asc",
        "sort": "ticker",
        "apiKey": api_key,
    }
    url = _build_options_url(base_url, symbol)
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results", [])
    if not isinstance(results, list):
        raise RuntimeError(f"Unexpected response shape: {data}")
    return results


def _safe_mid(bid: Optional[float], ask: Optional[float]) -> Optional[float]:
    if bid is None or ask is None:
        return None
    try:
        return round((float(bid) + float(ask)) / 2, 4)
    except Exception:
        return None


def _normalize_contract(raw: Dict[str, Any]) -> Dict[str, Any]:
    details = raw.get("details", {}) or {}
    last_quote = raw.get("last_quote", {}) or {}
    last_trade = raw.get("last_trade", {}) or {}
    greeks = raw.get("greeks", {}) or {}
    underlying = raw.get("underlying_asset", {}) or {}
    day = raw.get("day", {}) or {}

    bid = last_quote.get("bid")
    ask = last_quote.get("ask")

    return {
        "ticker": details.get("ticker"),
        "expiration": details.get("expiration_date") or details.get("expiration"),
        "strike": details.get("strike_price"),
        "type": details.get("contract_type"),
        "bid": bid,
        "ask": ask,
        "mid": _safe_mid(bid, ask),
        "last": (last_trade or {}).get("price"),
        "iv": raw.get("implied_volatility") or greeks.get("iv") or greeks.get("implied_volatility"),
        "delta": greeks.get("delta"),
        "gamma": greeks.get("gamma"),
        "theta": greeks.get("theta"),
        "vega": greeks.get("vega"),
        "volume": day.get("volume") or (last_trade or {}).get("size"),
        "oi": raw.get("open_interest"),
        "underlying": underlying.get("price"),
        "updated": raw.get("updated_at") or raw.get("timestamp"),
    }


def _derive_spot(contracts: List[Dict[str, Any]]) -> Optional[float]:
    for c in contracts:
        spot = c.get("underlying")
        if spot is not None:
            try:
                return float(spot)
            except Exception:
                continue
    return None


# ---------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------
def run_once(config: dict, log):
    start = time.perf_counter()
    api_key = config.get("api_key") or os.getenv("MASSIVE_API_KEY")
    if not api_key:
        log("chainfeed", "⛔️", "MASSIVE_API_KEY not set — skipping pull")
        return

    comp = config.get("component", {}) or {}
    workflow = comp.get("workflow", {}) or {}

    # Symbol defaults to SPX index; allow override via env or truth.workflow.symbol
    raw_symbol = os.getenv("CHAIN_SYMBOL") or workflow.get("symbol") or "SPX"
    symbol = raw_symbol if raw_symbol.startswith("I:") else f"I:{raw_symbol}"

    base_url = config.get("massive_base_url", "https://api.massive.com/v3/snapshot/options")
    limit = int(os.getenv("MASSIVE_CHAIN_LIMIT", "250"))
    maxlen = int(config.get("chain_stream_maxlen", 500))

    # Market redis client (prefer injected)
    r_market = config.get("r_market")
    if not r_market:
        r_market = _redis_from_url(os.getenv("MARKET_REDIS_URL", "redis://127.0.0.1:6380"))

    try:
        raw_chain = _fetch_chain(symbol, api_key, base_url, limit=limit)
    except Exception as e:
        log("chainfeed", "❌", f"Failed to pull chain for {symbol}: {e}")
        return

    contracts = [_normalize_contract(c) for c in raw_chain]
    spot = _derive_spot(contracts)
    ts = datetime.now(timezone.utc).isoformat()

    payload = {
        "symbol": symbol,
        "ts": ts,
        "spot": spot,
        "count": len(contracts),
        "contracts": contracts,
        "meta": {
            "source": "massive",
            "elapsed_sec": time.perf_counter() - start,
        },
    }

    chain_key = f"market:chain:{symbol}:latest"
    try:
        r_market.set(chain_key, json.dumps(payload), ex=120)
        r_market.xadd(
            "sse:chain-feed",
            {"json": json.dumps(payload)},
            maxlen=maxlen,
            approximate=True,
        )
        log("chainfeed", "✅", f"{symbol} chain → {chain_key} ({len(contracts)} contracts)")
    except Exception as e:
        log("chainfeed", "❌", f"Redis publish failed: {e}")
