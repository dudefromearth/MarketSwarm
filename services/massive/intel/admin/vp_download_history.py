#!/usr/bin/env python3
"""
VP Download History - Download minute bar history from Polygon

Downloads 1-minute bars for a ticker and saves to JSON file.
Used by the VP Admin menu for bulk historical data acquisition.

Usage:
    python vp_download_history.py --ticker SPY --years 5 --out-dir ./data/vp
    python vp_download_history.py --ticker QQQ --years max --out-dir ./data/vp
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
import time
from datetime import datetime, timedelta, date
from pathlib import Path

POLYGON_BASE = "https://api.polygon.io"

# Polygon free tier started around 2010, 15 years is practical max
MAX_YEARS = 15


class VPHistoryDownloader:
    def __init__(self, api_key: str, ticker: str, out_dir: Path):
        self.api_key = api_key
        self.ticker = ticker.upper()
        self.out_dir = out_dir
        self.bars: list[dict] = []
        self.days_processed = 0
        self.total_volume = 0

    def fetch_day(self, date_str: str) -> list[dict]:
        """Fetch minute bars for a single day."""
        url = (
            f"{POLYGON_BASE}/v2/aggs/ticker/{self.ticker}/range/1/minute/"
            f"{date_str}/{date_str}?apiKey={self.api_key}&limit=50000&sort=asc"
        )

        try:
            req = urllib.request.Request(url)
            req.add_header("User-Agent", "MarketSwarm/1.0")

            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
                return data.get("results", [])

        except urllib.error.HTTPError as e:
            if e.code == 429:
                print("  Rate limited, waiting 60s...")
                time.sleep(60)
                return self.fetch_day(date_str)
            print(f"  HTTP error {e.code} for {date_str}")
            return []
        except Exception as e:
            print(f"  Error fetching {date_str}: {e}")
            return []

    def download(self, years: int):
        """Download N years of history."""
        end_date = date.today()
        start_date = end_date - timedelta(days=years * 365)

        print(f"Downloading {self.ticker} data from {start_date} to {end_date}")
        print(f"Estimated trading days: ~{years * 252}")

        current = start_date
        last_progress = 0

        while current <= end_date:
            # Skip weekends
            if current.weekday() >= 5:
                current += timedelta(days=1)
                continue

            date_str = current.strftime("%Y-%m-%d")
            day_bars = self.fetch_day(date_str)

            if day_bars:
                self.bars.extend(day_bars)
                self.days_processed += 1
                day_volume = sum(b.get("v", 0) for b in day_bars)
                self.total_volume += day_volume

                # Progress every 50 days
                if self.days_processed - last_progress >= 50:
                    last_progress = self.days_processed
                    print(
                        f"  {self.days_processed} days ({current}): "
                        f"{len(self.bars):,} bars, {self.total_volume:,.0f} volume"
                    )

            # Rate limit: 5 requests/sec for free tier
            time.sleep(0.25)
            current += timedelta(days=1)

        print(
            f"\nDownload complete: {self.days_processed} days, "
            f"{len(self.bars):,} bars, {self.total_volume:,.0f} total volume"
        )

    def save(self) -> Path:
        """Save bars to JSON file."""
        self.out_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.ticker}_{self.days_processed}d_{timestamp}.json"
        filepath = self.out_dir / filename

        output = {
            "ticker": self.ticker,
            "days_processed": self.days_processed,
            "total_volume": self.total_volume,
            "bar_count": len(self.bars),
            "downloaded_at": datetime.now().isoformat(),
            "bars": self.bars,
        }

        with open(filepath, "w") as f:
            json.dump(output, f)

        size_mb = filepath.stat().st_size / (1024 * 1024)
        print(f"\nSaved to: {filepath}")
        print(f"File size: {size_mb:.1f} MB")

        return filepath


def main():
    parser = argparse.ArgumentParser(description="VP Download History")
    parser.add_argument(
        "--ticker", required=True, help="Ticker symbol (e.g., SPY, QQQ)"
    )
    parser.add_argument(
        "--years",
        required=True,
        help="Years of history to download (number or 'max')",
    )
    parser.add_argument(
        "--out-dir", required=True, help="Output directory for JSON file"
    )
    args = parser.parse_args()

    api_key = os.environ.get("POLYGON_API_KEY") or os.environ.get("MASSIVE_API_KEY")
    if not api_key:
        print("Error: POLYGON_API_KEY or MASSIVE_API_KEY environment variable required")
        sys.exit(1)

    # Parse years
    if args.years.lower() == "max":
        years = MAX_YEARS
    else:
        try:
            years = int(args.years)
            if years <= 0 or years > MAX_YEARS:
                print(f"Years must be between 1 and {MAX_YEARS}")
                sys.exit(1)
        except ValueError:
            print(f"Invalid years value: {args.years}")
            sys.exit(1)

    out_dir = Path(args.out_dir)

    downloader = VPHistoryDownloader(api_key, args.ticker, out_dir)
    downloader.download(years)
    downloader.save()


if __name__ == "__main__":
    main()
