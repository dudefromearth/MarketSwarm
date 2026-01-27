#!/usr/bin/env python3
"""
vp_download_history.py

Download 1-minute bars from Polygon and write to a JSON file:

{
  "ticker": "SPY",
  "start": "YYYY-MM-DD",
  "end": "YYYY-MM-DD",
  "bars": [ ... raw Polygon results ... ]
}

Usage examples:

  python vp_download_history.py --ticker SPY --years 5 --out-dir ./data/vp
  python vp_download_history.py --ticker QQQ --start 2020-01-01 --end 2024-12-31 --out out.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import requests


POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "")
POLYGON_API = "https://api.polygon.io"


def log(stage: str, emoji: str, msg: str) -> None:
    print(f"[vp_dl|{stage}]{emoji} {msg}")


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()

    ap.add_argument("--ticker", type=str, required=True,
                    help="Underlying ETF (e.g. SPY, QQQ)")
    ap.add_argument("--years", type=str, required=False,
                    help="Number of years (N|max). Mutually exclusive with --start/--end.")
    ap.add_argument("--start", type=str, required=False,
                    help="Explicit start date YYYY-MM-DD")
    ap.add_argument("--end", type=str, required=False,
                    help="Explicit end date YYYY-MM-DD")
    ap.add_argument("--out", type=str, required=False,
                    help="Output JSON file; default derived from ticker/start/end.")
    ap.add_argument("--out-dir", type=str, required=False,
                    help="Directory for output file if --out is not given.")

    return ap.parse_args()


def resolve_dates(args: argparse.Namespace) -> tuple[str, str]:
    if args.start and args.end:
        return args.start, args.end

    if not args.years:
        raise SystemExit("Error: You must provide either --years or both --start and --end")

    yrs = args.years
    today = date.today()

    if yrs == "max":
        if args.ticker.upper() == "SPY":
            start = date(1993, 1, 29)
        elif args.ticker.upper() == "QQQ":
            start = date(1999, 3, 10)
        else:
            # fallback: 10 years for unknown tickers
            start = today - timedelta(days=10 * 365)
    else:
        try:
            n = int(yrs)
        except ValueError:
            raise SystemExit(f"Invalid years value: {yrs}")
        start = today - timedelta(days=n * 365)

    return start.isoformat(), today.isoformat()


def http_get(url: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    if not POLYGON_API_KEY:
        log("http", "❌", "POLYGON_API_KEY not set in environment")
        return None

    headers = {"Authorization": f"Bearer {POLYGON_API_KEY}"}
    if params is None:
        params = {}
    params["apiKey"] = POLYGON_API_KEY

    for attempt in range(5):
        r = requests.get(url, params=params, headers=headers)
        if r.status_code == 429:
            # rate limit, back off briefly
            time.sleep(0.25)
            continue
        if r.status_code in (401, 403):
            log("http", "❌", f"AUTH ERROR {r.status_code}: {r.text}")
            return None
        if not r.ok:
            log("http", "❌", f"HTTP {r.status_code}: {r.text}")
            return None
        try:
            return r.json()
        except Exception:
            log("http", "❌", "Bad JSON response from Polygon")
            return None
    return None


def get_minute_bars(ticker: str, start_ymd: str, end_ymd: str) -> List[Dict[str, Any]]:
    url = f"{POLYGON_API}/v2/aggs/ticker/{ticker}/range/1/minute/{start_ymd}/{end_ymd}"
    params: Dict[str, Any] = {"adjusted": "true", "limit": 50000, "sort": "asc"}

    out: List[Dict[str, Any]] = []
    while True:
        data = http_get(url, params=params)
        if not data:
            break

        results = data.get("results") or []
        out.extend(results)

        next_url = data.get("next_url")
        if not next_url:
            break

        # keep passing apiKey explicitly
        url = next_url
        params = {"apiKey": POLYGON_API_KEY}

    return out


def main() -> None:
    args = parse_args()

    ticker = args.ticker.upper()
    start_ymd, end_ymd = resolve_dates(args)

    out_dir = args.out_dir or "."
    os.makedirs(out_dir, exist_ok=True)

    if args.out:
        out_path = args.out
    else:
        out_path = os.path.join(
            out_dir, f"{ticker}_1min_{start_ymd}_to_{end_ymd}.json"
        )

    log("config", "🔧", f"ticker={ticker}, start={start_ymd}, end={end_ymd}")
    log("config", "🔧", f"output={out_path}")

    bars = get_minute_bars(ticker, start_ymd, end_ymd)
    log("download", "ℹ️", f"Fetched {len(bars)} bars.")

    payload = {
        "ticker": ticker,
        "start": start_ymd,
        "end": end_ymd,
        "bars": bars,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)

    log("done", "✅", f"Wrote history to {out_path}")


if __name__ == "__main__":
    main()