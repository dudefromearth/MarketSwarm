#!/usr/bin/env python3
"""
strike-flow.py — Analyze per-strike tick activity for reversal signals.

Correlates:
- Strike-level tick activity (bids vs asks)
- Gamma exposure (GEX) at each strike
- Proximity to spot price
- Directional pressure (bid-heavy vs ask-heavy)

Usage:
    ./strike-flow.py                      # Current snapshot
    ./strike-flow.py --window 60          # Last 60 seconds aggregated
    ./strike-flow.py --window 300         # Last 5 minutes
    ./strike-flow.py --hot                # Show hottest strikes only
    ./strike-flow.py --near-spot 50       # Strikes within 50 points of spot
"""

import argparse
import asyncio
import json
from collections import defaultdict
from datetime import datetime

from redis.asyncio import Redis


SYMBOL = "I:SPX"


async def get_spot(r: Redis, symbol: str) -> float | None:
    raw = await r.get(f"massive:model:spot:{symbol}")
    if raw:
        return float(json.loads(raw).get("value"))
    return None


async def get_gex(r: Redis, symbol: str) -> dict:
    """Get GEX by strike (net call - put gamma exposure)."""
    calls_raw = await r.get(f"massive:gex:model:{symbol}:calls")
    puts_raw = await r.get(f"massive:gex:model:{symbol}:puts")

    calls = json.loads(calls_raw) if calls_raw else {}
    puts = json.loads(puts_raw) if puts_raw else {}

    gex_by_strike = {}

    # Combine expirations
    for exp, strikes in calls.get("expirations", {}).items():
        for strike, gex in strikes.items():
            gex_by_strike[int(strike)] = gex_by_strike.get(int(strike), 0) + gex

    for exp, strikes in puts.get("expirations", {}).items():
        for strike, gex in strikes.items():
            gex_by_strike[int(strike)] = gex_by_strike.get(int(strike), 0) - gex

    return gex_by_strike


async def get_hot_strikes(r: Redis, symbol: str) -> dict:
    """Get current hot strikes snapshot."""
    data = await r.hgetall(f"massive:ws:strike:hot:{symbol}")
    result = {}
    for strike, json_str in data.items():
        result[int(strike)] = json.loads(json_str)
    return result


async def get_strike_stream(r: Redis, symbol: str, window_sec: int) -> dict:
    """Aggregate strike activity over time window."""
    now = datetime.now().timestamp()
    start_ts = now - window_sec
    start_id = f"{int(start_ts * 1000)}-0"

    results = await r.xrange(f"massive:ws:strike:stream:{symbol}", min=start_id)

    aggregated = defaultdict(lambda: {"ticks": 0, "bids": 0, "asks": 0, "calls": 0, "puts": 0})

    for entry_id, fields in results:
        data = json.loads(fields.get("data", "{}"))
        for strike_str, stats in data.items():
            strike = int(strike_str)
            aggregated[strike]["ticks"] += stats.get("ticks", 0)
            aggregated[strike]["bids"] += stats.get("bids", 0)
            aggregated[strike]["asks"] += stats.get("asks", 0)
            aggregated[strike]["calls"] += stats.get("calls", 0)
            aggregated[strike]["puts"] += stats.get("puts", 0)

    return dict(aggregated)


def analyze_reversal_signals(strikes: dict, gex: dict, spot: float):
    """
    Analyze strike activity for potential reversal signals.

    Signals:
    - High tick activity at gamma wall = MM hedging active
    - Bid-heavy at support = buyers defending
    - Ask-heavy at resistance = sellers defending
    - Call/Put imbalance = directional flow
    """
    signals = []

    for strike, stats in strikes.items():
        if stats["ticks"] < 3:
            continue

        gex_val = gex.get(strike, 0)
        distance = strike - spot
        pressure = stats["bids"] - stats["asks"]
        call_put_ratio = stats["calls"] / max(stats["puts"], 1)

        signal = {
            "strike": strike,
            "distance": distance,
            "ticks": stats["ticks"],
            "bids": stats["bids"],
            "asks": stats["asks"],
            "pressure": pressure,
            "gex": gex_val,
            "call_put_ratio": call_put_ratio,
            "signals": [],
        }

        # Gamma wall with activity
        if abs(gex_val) > 1e9 and stats["ticks"] > 5:
            wall_type = "CALL WALL" if gex_val > 0 else "PUT WALL"
            signal["signals"].append(f"{wall_type} ACTIVE")

        # Directional pressure
        if pressure > 3:
            signal["signals"].append("BID PRESSURE (bullish)")
        elif pressure < -3:
            signal["signals"].append("ASK PRESSURE (bearish)")

        # Near spot with high activity
        if abs(distance) < 20 and stats["ticks"] > 10:
            signal["signals"].append("ATM HOT")

        # Call/Put flow imbalance
        if call_put_ratio > 2:
            signal["signals"].append("CALL FLOW")
        elif call_put_ratio < 0.5:
            signal["signals"].append("PUT FLOW")

        if signal["signals"]:
            signals.append(signal)

    return signals


async def main():
    parser = argparse.ArgumentParser(description="Strike flow analysis")
    parser.add_argument("--symbol", default=SYMBOL)
    parser.add_argument("--window", type=int, help="Time window in seconds")
    parser.add_argument("--hot", action="store_true", help="Show hot strikes only")
    parser.add_argument("--near-spot", type=int, help="Filter to strikes within N points of spot")
    args = parser.parse_args()

    r = Redis.from_url("redis://127.0.0.1:6380", decode_responses=True)

    spot = await get_spot(r, args.symbol)
    gex = await get_gex(r, args.symbol)

    if args.window:
        strikes = await get_strike_stream(r, args.symbol, args.window)
        label = f"Last {args.window}s"
    else:
        strikes = await get_hot_strikes(r, args.symbol)
        label = "Current snapshot"

    if args.near_spot and spot:
        strikes = {k: v for k, v in strikes.items() if abs(k - spot) <= args.near_spot}

    print(f"\n=== Strike Flow Analysis: {args.symbol} ({label}) ===")
    print(f"Spot: {spot:.2f}" if spot else "Spot: N/A")
    print()

    if not strikes:
        print("No strike activity data available yet.")
        await r.aclose()
        return

    # Sort by distance from spot
    if spot:
        sorted_strikes = sorted(strikes.items(), key=lambda x: abs(x[0] - spot))
    else:
        sorted_strikes = sorted(strikes.items(), key=lambda x: x[1].get("ticks", 0), reverse=True)

    print(f"{'Strike':<8} {'Dist':>6} {'Ticks':>6} {'Bids':>5} {'Asks':>5} {'Press':>6} {'GEX':>12} {'C/P':>5}")
    print("-" * 70)

    for strike, stats in sorted_strikes[:25]:
        ticks = stats.get("ticks", 0)
        if ticks == 0:
            continue

        bids = stats.get("bids", 0)
        asks = stats.get("asks", 0)
        pressure = bids - asks
        gex_val = gex.get(strike, 0)
        calls = stats.get("calls", 0)
        puts = stats.get("puts", 0)
        cp_ratio = calls / max(puts, 1)
        dist = (strike - spot) if spot else 0

        # Highlight row
        highlight = ""
        if abs(gex_val) > 1e9:
            highlight = " <-- GAMMA WALL"
        elif ticks > 10 and abs(pressure) > 5:
            highlight = " <-- PRESSURE"

        print(f"{strike:<8} {dist:>+6.0f} {ticks:>6} {bids:>5} {asks:>5} {pressure:>+6} {gex_val:>12.0f} {cp_ratio:>5.1f}{highlight}")

    # Reversal signals
    if spot:
        signals = analyze_reversal_signals(strikes, gex, spot)
        if signals:
            print(f"\n=== Potential Reversal Signals ===\n")
            for sig in sorted(signals, key=lambda x: abs(x["distance"])):
                print(f"Strike {sig['strike']} ({sig['distance']:+.0f} from spot):")
                for s in sig["signals"]:
                    print(f"  - {s}")
                print()

    await r.aclose()


if __name__ == "__main__":
    asyncio.run(main())
