# services/massive/intel/utils/get_spot.py

"""
get_spot.py — Massive index spot utility

Library usage:
    from intel.utils.get_spot import MassiveSpotClient

    client = MassiveSpotClient(api_key=config["env"]["MASSIVE_API_KEY"])
    spx_spot = client.get_spot("I:SPX")
    vix_spot = client.get_spot("I:VIX")

CLI usage (dev/debug):
    python get_spot.py I:SPX --mode=spot|json|pretty
"""

from __future__ import annotations

import os
import sys
import json
import urllib.parse
from typing import Literal

import requests

BASE_URL = os.getenv("MASSIVE_BASE_URL", "https://api.massive.com/v3/snapshot")


class MassiveSpotClient:
    """
    Thin wrapper around Massive's /v3/snapshot endpoint for index spot.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        session: requests.Session | None = None,
        timeout: float = 10.0,
    ) -> None:
        if not api_key:
            raise ValueError("MassiveSpotClient requires a non-empty api_key")

        self.api_key = api_key
        self.base_url = base_url or BASE_URL
        self.session = session or requests.Session()
        self.timeout = timeout

    def fetch_index_snapshot(self, symbol: str) -> dict:
        """
        Fetch raw Massive JSON snapshot for an index (e.g. I:SPX, I:NDX, I:VIX).
        """
        if not symbol.startswith("I:"):
            raise ValueError("Symbol must be an index (format: I:XXXX)")

        encoded_symbol = urllib.parse.quote(symbol)
        url = (
            f"{self.base_url}?ticker={encoded_symbol}"
            f"&order=asc&limit=10&sort=ticker&apiKey={self.api_key}"
        )

        resp = self.session.get(url, timeout=self.timeout)
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP Error {resp.status_code}: {resp.text}")

        data = resp.json()
        if isinstance(data, dict) and "error" in data:
            raise RuntimeError(f"Massive API Error: {data['error']}")

        return data

    @staticmethod
    def extract_spot(data: dict, symbol: str) -> float:
        """
        Extracts only the numeric spot price from the raw Massive JSON.
        """
        results = data.get("results", [])
        if not results:
            raise RuntimeError(f"No results returned for {symbol}")

        spot = results[0].get("value")
        if spot is None:
            raise RuntimeError(f"Spot value missing in Massive response for {symbol}")

        return float(spot)

    def get_spot(self, symbol: str) -> float:
        """
        Convenience: fetch snapshot and return numeric spot.
        """
        data = self.fetch_index_snapshot(symbol)
        return self.extract_spot(data, symbol)


# ------------------------------------------------------------
# CLI entrypoint (optional, for dev/debug)
# ------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python get_spot.py <symbol> [--mode=spot|json|pretty]")
        sys.exit(1)

    symbol = sys.argv[1].strip().upper()
    mode: Literal["spot", "json", "pretty"] = "spot"

    # Parse optional --mode flag
    for arg in sys.argv[2:]:
        if arg.startswith("--mode="):
            mode = arg.split("=", 1)[1].strip().lower()  # type: ignore[assignment]

    api_key = os.getenv("MASSIVE_API_KEY", "")

    try:
        client = MassiveSpotClient(api_key=api_key)
        data = client.fetch_index_snapshot(symbol)

        if mode == "spot":
            spot = client.extract_spot(data, symbol)
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