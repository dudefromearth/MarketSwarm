#!/usr/bin/env python3

import asyncio
from redis.asyncio import Redis
import json
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime
import argparse

DEFAULT_SYMBOL = "I:SPX"
DEFAULT_STRATEGY = "butterfly"
DEFAULT_SIDE = "call"

async def fetch_models(symbol):
    r = Redis.from_url("redis://127.0.0.1:6380", decode_responses=True)

    # Single latest model key (combined)
    heatmap_raw = await r.get(f"massive:heatmap:model:{symbol}:latest")
    heatmap_model = json.loads(heatmap_raw) if heatmap_raw else None

    # GEX (unchanged)
    calls_raw = await r.get(f"massive:gex:model:{symbol}:calls")
    puts_raw = await r.get(f"massive:gex:model:{symbol}:puts")
    calls_model = json.loads(calls_raw) if calls_raw else {}
    puts_model = json.loads(puts_raw) if puts_raw else {}

    await r.aclose()
    return heatmap_model, calls_model, puts_model

def plot_side_by_side(heatmap_model, calls_model, puts_model, symbol, strategy, side):
    if not heatmap_model:
        print("No heatmap model available — waiting for chain snapshot")
        fig = plt.figure(figsize=(16, 10), facecolor='black')
        fig.text(0.5, 0.5, "Market Closed", ha='center', va='center', fontsize=30, color='gray')
        fig.text(0.5, 0.4, "Showing last session data\nNew data at open tomorrow",
                 ha='center', va='center', fontsize=16, color='darkgray')
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        outfile = f"heatmap_gex_{timestamp}.png"
        plt.savefig(outfile, dpi=150, bbox_inches='tight', facecolor='black')
        print(f"Plot saved as {outfile}")
        return

    # Extract the requested strategy/side from combined model
    if strategy == "single":
        tiles = heatmap_model.get("single", {})
        if not tiles:
            print("No single tiles in model")
            return
        widths = ["Call", "Put"]
        grid = np.full((len(tiles), 2), np.nan)
        strikes = sorted([float(s) for s in tiles.keys()], reverse=True)
        for i, strike_str in enumerate(strikes):
            tile = tiles.get(strike_str, {})
            grid[i, 0] = tile.get("call", {}).get("value", np.nan)
            grid[i, 1] = tile.get("put", {}).get("value", np.nan)
        title = f'Convexity Heatmap\n{symbol} - Single (Call / Put)'
    else:
        key = f"{strategy}_{side}"
        strategy_tiles = heatmap_model.get(key, {})
        if not strategy_tiles:
            print(f"No tiles for {key} in model")
            return
        tiles = strategy_tiles

        # Dynamic widths
        sample = next(iter(tiles.values()), {})
        widths = sorted([int(w) for w in sample.keys() if w.isdigit()], key=int)
        if not widths:
            widths = [20, 25, 30, 35, 40, 45, 50]

        strikes = sorted([float(s) for s in tiles.keys()], reverse=True)
        grid = np.full((len(strikes), len(widths)), np.nan)
        for i, strike_str in enumerate(strikes):
            strike_tiles = tiles.get(strike_str, {})
            for j, w in enumerate(widths):
                w_str = str(w)
                val = strike_tiles.get(w_str)
                if isinstance(val, dict):
                    val = val.get("value")
                if val is not None:
                    grid[i, j] = val

        title = f'Convexity Heatmap\n{symbol} - {strategy.capitalize()} - {side.capitalize()}'

    # GEX
    gex_strikes = []
    gex_values = []
    expirations = calls_model.get("expirations", {})
    if expirations:
        exp_key = next(iter(expirations))
        exp_data = expirations[exp_key]
        put_data = puts_model.get("expirations", {}).get(exp_key, {})
        for s_str in sorted(exp_data.keys(), key=float, reverse=True):
            s = float(s_str)
            gex_strikes.append(s)
            gex_values.append(exp_data.get(s_str, 0) - put_data.get(s_str, 0))
        gex_title = exp_key
    else:
        gex_title = "N/A"

    fig = plt.figure(figsize=(16, 10), facecolor='black')
    gs = fig.add_gridspec(1, 2, width_ratios=[1, 3], wspace=0.05)

    ax_gex = fig.add_subplot(gs[0])
    ax_gex.set_facecolor('black')
    if gex_values:
        colors = ['green' if v > 0 else 'red' for v in gex_values]
        ax_gex.barh(gex_strikes, gex_values, color=colors)
        ax_gex.invert_yaxis()
    ax_gex.set_xlabel('Gamma Exposure', color='white')
    ax_gex.set_title(f'Gamma Exposure\n{symbol}\nExpiry {gex_title}', color='white')
    ax_gex.axvline(0, color='gray', linewidth=0.8)
    ax_gex.tick_params(colors='white')

    ax_heat = fig.add_subplot(gs[1])
    ax_heat.set_facecolor('black')
    im = ax_heat.imshow(grid, cmap='viridis', aspect='auto', origin='upper')
    ax_heat.set_xticks(np.arange(len(widths)))
    ax_heat.set_xticklabels(widths, color='white')
    ax_heat.set_yticks(np.arange(len(strikes)))
    ax_heat.set_yticklabels([int(s) for s in strikes], color='white')
    ax_heat.set_title(title, color='white')
    ax_heat.set_xlabel('Width' if strategy != "single" else 'Side', color='white')
    ax_heat.tick_params(colors='white')

    for i in range(len(strikes)):
        for j in range(len(widths)):
            val = grid[i, j]
            if not np.isnan(val):
                ax_heat.text(j, i, f'{val:.2f}', ha='center', va='center', color='white', fontsize=8)

    spot = 6899.93
    if strikes and min(strikes) <= spot <= max(strikes):
        spot_idx = np.searchsorted(strikes[::-1], spot) - 1
        ax_heat.axhline(spot_idx, color='yellow', linewidth=2, linestyle='--')
        ax_gex.axhline(spot_idx, color='yellow', linewidth=2, linestyle='--')
        ax_heat.text(len(widths), spot_idx, f' Spot {spot}', color='yellow', va='center', ha='left', fontweight='bold')

    plt.suptitle(f'{symbol} - {strategy.capitalize()} - {"Call/Put" if strategy == "single" else side.capitalize()}', color='white')
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    outfile = f"heatmap_gex_{timestamp}.png"
    plt.savefig(outfile, dpi=150, bbox_inches='tight', facecolor='black')
    print(f"Plot saved as {outfile}")

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbol', default=DEFAULT_SYMBOL)
    parser.add_argument('--strategy', default=DEFAULT_STRATEGY, choices=['butterfly', 'vertical', 'single'])
    parser.add_argument('--side', default=DEFAULT_SIDE, choices=['call', 'put'])
    args = parser.parse_args()

    heatmap, calls, puts = await fetch_models(args.symbol)

    plot_side_by_side(heatmap, calls, puts, args.symbol, args.strategy, args.side)

if __name__ == "__main__":
    asyncio.run(main())