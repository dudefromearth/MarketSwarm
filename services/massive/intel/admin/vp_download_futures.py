#!/usr/bin/env python3
"""
vp_download_futures.py

Download ES/NQ futures daily OHLCV bars from yfinance and save in the
same JSON format as vp_download_history.py (Polygon minute bars).

ES prices are already at SPX scale (multiplier=1 in vp_build_profile).
NQ prices are already at NDX scale (multiplier=1).

Usage:
    python vp_download_futures.py --ticker ES --out-dir ./data/vp
    python vp_download_futures.py --ticker NQ --out-dir ./data/vp
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import yfinance as yf

# Map our short names to yfinance tickers
TICKER_MAP = {
    "ES": "ES=F",
    "NQ": "NQ=F",
}


def log(stage: str, emoji: str, msg: str) -> None:
    print(f"[vp_futures|{stage}]{emoji} {msg}")


def download_futures(ticker: str, out_dir: Path) -> Path:
    yf_ticker = TICKER_MAP.get(ticker)
    if not yf_ticker:
        raise SystemExit(
            f"Unsupported ticker: {ticker}. Supported: {list(TICKER_MAP)}"
        )

    log("download", "📡", f"Downloading {yf_ticker} daily bars (period=max)...")

    df = yf.download(yf_ticker, period="max", interval="1d", progress=False)

    if df.empty:
        raise SystemExit(f"No data returned for {yf_ticker}")

    # yfinance returns MultiIndex columns when downloading a single ticker
    # with newer versions — flatten if needed
    if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
        df.columns = df.columns.get_level_values(0)

    log("download", "ℹ️", f"Got {len(df)} daily bars from {df.index[0].date()} to {df.index[-1].date()}")

    # Convert to bar dicts matching Polygon format
    bars = []
    total_volume = 0

    for ts, row in df.iterrows():
        o = float(row["Open"])
        h = float(row["High"])
        l = float(row["Low"])
        c = float(row["Close"])
        v = float(row["Volume"])

        # Skip zero-volume or NaN rows
        if v <= 0 or any(x != x for x in (o, h, l, c, v)):
            continue

        # Convert timestamp to epoch milliseconds (matching Polygon format)
        epoch_ms = int(ts.timestamp() * 1000)

        bars.append({"o": o, "h": h, "l": l, "c": c, "v": v, "t": epoch_ms})
        total_volume += v

    # Count unique trading days
    days_processed = len(bars)

    log("process", "📊", f"Processed {days_processed} daily bars, total volume: {total_volume:,.0f}")

    # Build output payload (matches vp_download_history.py format)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{ticker}_{days_processed}d_{timestamp}.json"
    out_dir.mkdir(parents=True, exist_ok=True)
    filepath = out_dir / filename

    output = {
        "ticker": ticker,
        "days_processed": days_processed,
        "total_volume": total_volume,
        "bar_count": len(bars),
        "resolution": "daily",
        "downloaded_at": datetime.now().isoformat(),
        "bars": bars,
    }

    with open(filepath, "w") as f:
        json.dump(output, f)

    size_mb = filepath.stat().st_size / (1024 * 1024)
    log("save", "💾", f"Saved to: {filepath} ({size_mb:.1f} MB)")

    return filepath


def main():
    ap = argparse.ArgumentParser(
        description="Download ES/NQ futures daily bars from yfinance"
    )
    ap.add_argument(
        "--ticker",
        type=str,
        required=True,
        help="Futures ticker short name (ES or NQ)",
    )
    ap.add_argument(
        "--out-dir",
        type=str,
        required=True,
        help="Output directory for JSON file",
    )
    args = ap.parse_args()

    ticker = args.ticker.upper()
    out_dir = Path(args.out_dir)

    download_futures(ticker, out_dir)


if __name__ == "__main__":
    main()
