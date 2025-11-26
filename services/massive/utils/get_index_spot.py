#!/usr/bin/env python3
"""
get_index_spot.py — Universal Index Spot Retriever
--------------------------------------------------

Supports three output modes:
  --mode=spot    → numeric spot price only
  --mode=json    → raw Massive JSON
  --mode=pretty  → indented JSON, jq-like formatting

Usage:
    python get_index_spot.py I:SPX
    python get_index_spot.py I:NDX --mode=pretty
    python get_index_spot.py I:VIX --mode=json
"""

import os
import sys
import requests
import urllib.parse
import json


BASE_URL = "https://api.massive.com/v3/snapshot"
API_KEY = os.getenv("MASSIVE_API_KEY", "pdjraOWSpDbg3ER_RslZYe3dmn4Y7WCC")


# ------------------------------------------------------------
# Core HTTP fetcher
# ------------------------------------------------------------
def fetch_index_snapshot(symbol: str, api_key: str = API_KEY):
    """Fetch raw Massive JSON snapshot for an index."""
    if not symbol.startswith("I:"):
        raise ValueError("Symbol must be an index (format: I:XXXX)")

    encoded_symbol = urllib.parse.quote(symbol)

    url = (
        f"{BASE_URL}?ticker={encoded_symbol}"
        f"&order=asc&limit=10&sort=ticker&apiKey={api_key}"
    )

    resp = requests.get(url, timeout=10)

    if resp.status_code != 200:
        raise RuntimeError(f"HTTP Error {resp.status_code}: {resp.text}")

    data = resp.json()

    if "error" in data:
        raise RuntimeError(f"Massive API Error: {data['error']}")

    return data


def extract_spot(data: dict, symbol: str) -> float:
    """Extracts only the numeric spot price from the raw JSON."""
    results = data.get("results", [])
    if not results:
        raise RuntimeError(f"No results returned for {symbol}")

    spot = results[0].get("value")
    if spot is None:
        raise RuntimeError(f"Spot value missing in Massive response for {symbol}")

    return float(spot)


# ------------------------------------------------------------
# CLI Entry Point
# ------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python get_index_spot.py <symbol> [--mode=spot|json|pretty]")
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