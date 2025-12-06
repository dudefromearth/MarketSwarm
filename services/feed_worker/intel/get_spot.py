#!/usr/bin/env python3
"""
get_spot.py — Universal Index Spot Retriever (Massive)
------------------------------------------------------

Supports three output modes for CLI:
  --mode=spot    → numeric spot price only
  --mode=json    → raw Massive JSON
  --mode=pretty  → indented JSON, jq-like formatting

Module API (for dte_feed_worker):

    from get_spot import get_spot

    spot = get_spot("I:SPX")                    # uses MASSIVE_API_KEY from env
    spot = get_spot("I:SPX", api_key="...")     # explicit API key override
"""

import os
import sys
import requests
import urllib.parse
import json
from typing import Any, Dict, Optional


BASE_URL = os.getenv("MASSIVE_SNAPSHOT_URL", "https://api.massive.com/v3/snapshot")
API_KEY = os.getenv("MASSIVE_API_KEY", "")


# ------------------------------------------------------------
# Core HTTP fetcher
# ------------------------------------------------------------
def fetch_index_snapshot(symbol: str, api_key: Optional[str] = None) -> Dict[str, Any]:
    """Fetch raw Massive JSON snapshot for an index."""
    if not symbol.startswith("I:"):
        raise ValueError("Symbol must be an index (format: I:XXXX)")

    key = api_key or API_KEY
    if not key:
        raise RuntimeError("MASSIVE_API_KEY not set (and no api_key passed)")

    encoded_symbol = urllib.parse.quote(symbol)

    url = (
        f"{BASE_URL}?ticker={encoded_symbol}"
        f"&order=asc&limit=10&sort=ticker"
    )

    resp = requests.get(url, params={"apiKey": key}, timeout=10)

    if resp.status_code != 200:
        raise RuntimeError(f"HTTP Error {resp.status_code}: {resp.text}")

    data = resp.json()

    if isinstance(data, dict) and "error" in data:
        raise RuntimeError(f"Massive API Error: {data['error']}")

    return data


def extract_spot(data: Dict[str, Any], symbol: str) -> float:
    """Extracts only the numeric spot price from the raw JSON."""
    results = data.get("results", [])
    if not results:
        raise RuntimeError(f"No results returned for {symbol}")

    spot = results[0].get("value")
    if spot is None:
        raise RuntimeError(f"Spot value missing in Massive response for {symbol}")

    return float(spot)


def get_spot(symbol: str, api_key: Optional[str] = None) -> float:
    """
    Primary programmatic entry point for services.

    Example:
        spot = get_spot("I:SPX")
    """
    data = fetch_index_snapshot(symbol, api_key=api_key)
    return extract_spot(data, symbol)


# ------------------------------------------------------------
# CLI Entry Point
# ------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python get_spot.py <symbol> [--mode=spot|json|pretty]")
        sys.exit(1)

    symbol = sys.argv[1].strip().upper()
    mode = "spot"  # default

    # Parse optional --mode flag
    for arg in sys.argv[2:]:
        if arg.startswith("--mode="):
            mode = arg.split("=", 1)[1].strip().lower()

    try:
        data = fetch_index_snapshot(symbol)

        if mode == "spot":
            spot = extract_spot(data, symbol)
            print(spot)

        elif mode == "json":
            print(json.dumps(data))

        elif mode == "pretty":
            print(json.dumps(data, indent=2))

        else:
            print(f"ERROR: Unsupported mode '{mode}'. Use spot, json, or pretty.")
            sys.exit(1)

    except Exception as e:
        print(json.dumps({"symbol": symbol, "error": str(e)}, indent=2))
        sys.exit(1)