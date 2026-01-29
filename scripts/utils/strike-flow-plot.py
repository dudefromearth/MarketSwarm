#!/usr/bin/env python3
"""
strike-flow-plot.py — Visualize strike-level tick activity over time.

Creates a multi-panel plot:
1. Strike activity heatmap (time x strike)
2. Directional pressure (bid vs ask) by strike
3. GEX overlay with gamma walls highlighted
4. Spot price trajectory

Usage:
    ./strike-flow-plot.py                     # Last 5 minutes
    ./strike-flow-plot.py --window 60         # Last 60 seconds
    ./strike-flow-plot.py --window 900        # Last 15 minutes
    ./strike-flow-plot.py --bucket 10s        # 10-second time buckets
    ./strike-flow-plot.py --live              # Live updating (refresh every 5s)
"""

import argparse
import asyncio
import json
from collections import defaultdict
from datetime import datetime
import time as time_module

import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.animation import FuncAnimation
import numpy as np
from redis.asyncio import Redis


SYMBOL = "I:SPX"
REDIS_URL = "redis://127.0.0.1:6380"


async def get_spot(r: Redis, symbol: str) -> float | None:
    raw = await r.get(f"massive:model:spot:{symbol}")
    if raw:
        return float(json.loads(raw).get("value"))
    return None


async def get_gex(r: Redis, symbol: str) -> dict:
    """Get GEX by strike."""
    calls_raw = await r.get(f"massive:gex:model:{symbol}:calls")
    puts_raw = await r.get(f"massive:gex:model:{symbol}:puts")

    calls = json.loads(calls_raw) if calls_raw else {}
    puts = json.loads(puts_raw) if puts_raw else {}

    gex_by_strike = {}

    for exp, strikes in calls.get("expirations", {}).items():
        for strike, gex in strikes.items():
            gex_by_strike[int(strike)] = gex_by_strike.get(int(strike), 0) + gex

    for exp, strikes in puts.get("expirations", {}).items():
        for strike, gex in strikes.items():
            gex_by_strike[int(strike)] = gex_by_strike.get(int(strike), 0) - gex

    return gex_by_strike


async def get_strike_stream(r: Redis, symbol: str, window_sec: int):
    """Fetch raw strike stream data."""
    now = datetime.now().timestamp()
    start_ts = now - window_sec
    start_id = f"{int(start_ts * 1000)}-0"

    results = await r.xrange(f"massive:ws:strike:stream:{symbol}", min=start_id)

    events = []
    for entry_id, fields in results:
        ts = float(fields.get("ts", 0))
        data = json.loads(fields.get("data", "{}"))
        events.append({"ts": ts, "strikes": data})

    return events


def bucket_data(events, bucket_sec: int, spot: float, strike_range: int = 100):
    """
    Bucket strike activity into time intervals.
    Returns grid for heatmap and pressure data.
    """
    if not events or not spot:
        return None, None, None, None

    # Determine strike range centered on spot, aligned to 5-point grid
    # Descending order (higher strikes at top)
    min_strike = int((spot - strike_range) // 5) * 5
    max_strike = int((spot + strike_range) // 5) * 5 + 5
    strikes = list(range(max_strike, min_strike - 1, -5))  # 5-point increments, descending

    # Determine time range
    min_ts = min(e["ts"] for e in events)
    max_ts = max(e["ts"] for e in events)

    # Create time buckets
    num_buckets = max(1, int((max_ts - min_ts) / bucket_sec) + 1)
    time_labels = []
    for i in range(num_buckets):
        t = min_ts + i * bucket_sec
        time_labels.append(datetime.fromtimestamp(t).strftime("%H:%M:%S"))

    # Initialize grids
    tick_grid = np.zeros((len(strikes), num_buckets))
    pressure_grid = np.zeros((len(strikes), num_buckets))

    # Fill grids
    strike_to_idx = {s: i for i, s in enumerate(strikes)}

    for event in events:
        bucket_idx = min(int((event["ts"] - min_ts) / bucket_sec), num_buckets - 1)

        for strike_str, stats in event["strikes"].items():
            strike = int(strike_str)
            # Round to nearest 5
            rounded = int(round(strike / 5) * 5)
            if rounded in strike_to_idx:
                idx = strike_to_idx[rounded]
                tick_grid[idx, bucket_idx] += stats.get("ticks", 0)
                pressure_grid[idx, bucket_idx] += stats.get("bids", 0) - stats.get("asks", 0)

    return tick_grid, pressure_grid, strikes, time_labels


async def fetch_all_data(symbol: str, window_sec: int):
    """Fetch all data needed for visualization."""
    r = Redis.from_url(REDIS_URL, decode_responses=True)

    spot = await get_spot(r, symbol)
    gex = await get_gex(r, symbol)
    events = await get_strike_stream(r, symbol, window_sec)

    await r.aclose()

    return spot, gex, events


def create_plot(spot, gex, events, bucket_sec, symbol):
    """Create the multi-panel visualization."""
    if not spot:
        print("No spot price available")
        return None

    tick_grid, pressure_grid, strikes, time_labels = bucket_data(
        events, bucket_sec, spot, strike_range=75
    )

    if tick_grid is None:
        print("No strike activity data available")
        return None

    fig = plt.figure(figsize=(16, 12), facecolor='black')
    fig.suptitle(f'{symbol} Strike Flow Analysis - Spot: {spot:.2f}', color='white', fontsize=14)

    gs = fig.add_gridspec(2, 2, height_ratios=[2, 1], width_ratios=[1, 3], hspace=0.15, wspace=0.1)

    # ===== Panel 1: GEX by strike (left) =====
    ax_gex = fig.add_subplot(gs[0, 0])
    ax_gex.set_facecolor('black')

    gex_values = [gex.get(s, 0) for s in strikes]
    colors = ['green' if v > 0 else 'red' for v in gex_values]
    y_pos = np.arange(len(strikes))

    ax_gex.barh(y_pos, gex_values, color=colors, alpha=0.7)
    ax_gex.set_yticks(y_pos[::5])
    ax_gex.set_yticklabels([strikes[i] for i in range(0, len(strikes), 5)], color='white', fontsize=8)
    ax_gex.set_xlabel('GEX', color='white')
    ax_gex.set_title('Gamma Exposure', color='white')
    ax_gex.axvline(0, color='gray', linewidth=0.5)
    ax_gex.tick_params(colors='white')

    # Spot line on GEX
    if spot in strikes:
        spot_idx = strikes.index(int(spot))
    else:
        spot_idx = min(range(len(strikes)), key=lambda i: abs(strikes[i] - spot))
    ax_gex.axhline(spot_idx, color='cyan', linewidth=2, linestyle='--')

    # ===== Panel 2: Tick activity heatmap (right top) =====
    ax_heat = fig.add_subplot(gs[0, 1])
    ax_heat.set_facecolor('black')

    # Mask zeros and use percentile-based normalization for contrast
    tick_display = tick_grid.copy()
    tick_display[tick_display == 0] = np.nan  # Hide zeros

    # Use non-zero values for normalization
    non_zero = tick_grid[tick_grid > 0]
    if len(non_zero) > 0:
        vmin = np.percentile(non_zero, 5)
        vmax = np.percentile(non_zero, 95)
    else:
        vmin, vmax = 0, 1

    im = ax_heat.imshow(tick_display, cmap='inferno', aspect='auto', origin='upper',
                        vmin=vmin, vmax=vmax)
    ax_heat.set_title('Tick Activity (log scale)', color='white')
    ax_heat.set_xlabel('Time', color='white')

    # X-axis: time labels (show every Nth)
    step = max(1, len(time_labels) // 10)
    ax_heat.set_xticks(range(0, len(time_labels), step))
    ax_heat.set_xticklabels([time_labels[i] for i in range(0, len(time_labels), step)], color='white', fontsize=8, rotation=45)

    # Y-axis: strike labels
    ax_heat.set_yticks(range(0, len(strikes), 5))
    ax_heat.set_yticklabels([strikes[i] for i in range(0, len(strikes), 5)], color='white', fontsize=8)

    ax_heat.tick_params(colors='white')

    # Spot line
    ax_heat.axhline(spot_idx, color='cyan', linewidth=2, linestyle='--')
    ax_heat.text(len(time_labels), spot_idx, f' Spot {spot:.0f}', color='cyan', va='center', fontsize=9)

    # Colorbar for tick heatmap
    cbar1 = plt.colorbar(im, ax=ax_heat, orientation='vertical', pad=0.02)
    cbar1.ax.yaxis.set_tick_params(color='white')
    cbar1.ax.set_ylabel('Ticks', color='white')
    plt.setp(plt.getp(cbar1.ax.axes, 'yticklabels'), color='white')

    # ===== Panel 3: Cumulative pressure by strike (left bottom) =====
    ax_press_cum = fig.add_subplot(gs[1, 0])
    ax_press_cum.set_facecolor('black')

    cumulative_pressure = pressure_grid.sum(axis=1)
    colors_press = ['green' if v > 0 else 'red' for v in cumulative_pressure]
    ax_press_cum.barh(y_pos, cumulative_pressure, color=colors_press, alpha=0.7)
    ax_press_cum.set_yticks(y_pos[::5])
    ax_press_cum.set_yticklabels([strikes[i] for i in range(0, len(strikes), 5)], color='white', fontsize=8)
    ax_press_cum.set_xlabel('Net Pressure (Bids - Asks)', color='white')
    ax_press_cum.set_title('Directional Pressure', color='white')
    ax_press_cum.axvline(0, color='gray', linewidth=0.5)
    ax_press_cum.tick_params(colors='white')
    ax_press_cum.axhline(spot_idx, color='cyan', linewidth=2, linestyle='--')

    # ===== Panel 4: Pressure heatmap over time (right bottom) =====
    ax_press = fig.add_subplot(gs[1, 1])
    ax_press.set_facecolor('black')

    # Mask zeros for pressure too
    pressure_display = pressure_grid.copy()
    pressure_display[pressure_grid == 0] = np.nan

    # Diverging colormap for pressure (green = bid heavy, red = ask heavy)
    non_zero_press = pressure_grid[pressure_grid != 0]
    if len(non_zero_press) > 0:
        max_abs = max(abs(np.percentile(non_zero_press, 5)), abs(np.percentile(non_zero_press, 95)), 1)
    else:
        max_abs = 1
    norm = mcolors.TwoSlopeNorm(vmin=-max_abs, vcenter=0, vmax=max_abs)

    im2 = ax_press.imshow(pressure_display, cmap='RdYlGn', aspect='auto', origin='upper', norm=norm)
    ax_press.set_title('Directional Pressure Over Time', color='white')
    ax_press.set_xlabel('Time', color='white')

    ax_press.set_xticks(range(0, len(time_labels), step))
    ax_press.set_xticklabels([time_labels[i] for i in range(0, len(time_labels), step)], color='white', fontsize=8, rotation=45)
    ax_press.set_yticks(range(0, len(strikes), 5))
    ax_press.set_yticklabels([strikes[i] for i in range(0, len(strikes), 5)], color='white', fontsize=8)
    ax_press.tick_params(colors='white')
    ax_press.axhline(spot_idx, color='cyan', linewidth=2, linestyle='--')

    # Colorbar
    cbar = plt.colorbar(im2, ax=ax_press, orientation='vertical', pad=0.02)
    cbar.ax.yaxis.set_tick_params(color='white')
    cbar.ax.set_ylabel('Pressure', color='white')
    plt.setp(plt.getp(cbar.ax.axes, 'yticklabels'), color='white')

    return fig


def parse_bucket(bucket_str: str) -> int:
    """Parse bucket size string to seconds."""
    if bucket_str.endswith("s"):
        return int(bucket_str[:-1])
    elif bucket_str.endswith("m"):
        return int(bucket_str[:-1]) * 60
    return int(bucket_str)


async def main():
    parser = argparse.ArgumentParser(description="Strike flow visualization")
    parser.add_argument("--symbol", default=SYMBOL)
    parser.add_argument("--window", type=int, default=300, help="Time window in seconds")
    parser.add_argument("--bucket", type=str, default="10s", help="Time bucket size")
    parser.add_argument("--live", action="store_true", help="Live updating mode")
    parser.add_argument("--output", type=str, help="Output file path (optional)")
    parser.add_argument("--debug", action="store_true", help="Show debug info")
    args = parser.parse_args()

    bucket_sec = parse_bucket(args.bucket)

    if args.debug:
        r = Redis.from_url(REDIS_URL, decode_responses=True)
        spot = await get_spot(r, args.symbol)
        print(f"Spot: {spot}")

        # Check stream length
        stream_len = await r.xlen(f"massive:ws:strike:stream:{args.symbol}")
        print(f"Stream length: {stream_len}")

        # Check time range
        now = datetime.now().timestamp()
        start_ts = now - args.window
        print(f"Query range: {datetime.fromtimestamp(start_ts)} to {datetime.fromtimestamp(now)}")

        # Fetch events
        events = await get_strike_stream(r, args.symbol, args.window)
        print(f"Events fetched: {len(events)}")

        if events:
            print(f"First event ts: {datetime.fromtimestamp(events[0]['ts'])}")
            print(f"Last event ts: {datetime.fromtimestamp(events[-1]['ts'])}")
            print(f"Sample strikes: {list(events[0]['strikes'].keys())[:10]}")

            # Check bucketing
            if spot:
                tick_grid, pressure_grid, strikes, time_labels = bucket_data(events, bucket_sec, spot)
                if tick_grid is not None:
                    print(f"Grid shape: {tick_grid.shape}")
                    print(f"Strike range: {strikes[0]} to {strikes[-1]}")
                    print(f"Non-zero cells: {np.count_nonzero(tick_grid)}")
                    print(f"Max value: {tick_grid.max()}")

        await r.aclose()
        return

    if args.live:
        print("Live mode - updating every 5 seconds (Ctrl+C to stop)")

        while True:
            spot, gex, events = await fetch_all_data(args.symbol, args.window)
            fig = create_plot(spot, gex, events, bucket_sec, args.symbol)

            if fig:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                outfile = f"strike_flow_{timestamp}.png"
                plt.savefig(outfile, dpi=120, bbox_inches='tight', facecolor='black')
                plt.close(fig)
                print(f"Saved: {outfile}")

            await asyncio.sleep(5)
    else:
        spot, gex, events = await fetch_all_data(args.symbol, args.window)
        fig = create_plot(spot, gex, events, bucket_sec, args.symbol)

        if fig:
            if args.output:
                outfile = args.output
            else:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                outfile = f"strike_flow_{timestamp}.png"

            plt.savefig(outfile, dpi=150, bbox_inches='tight', facecolor='black')
            print(f"Plot saved: {outfile}")
            plt.close(fig)


if __name__ == "__main__":
    asyncio.run(main())
