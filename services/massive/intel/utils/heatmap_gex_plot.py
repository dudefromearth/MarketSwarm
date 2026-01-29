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

    # GEX
    calls_raw = await r.get(f"massive:gex:model:{symbol}:calls")
    puts_raw = await r.get(f"massive:gex:model:{symbol}:puts")
    calls_model = json.loads(calls_raw) if calls_raw else {}
    puts_model = json.loads(puts_raw) if puts_raw else {}

    # Spot price
    spot_raw = await r.get(f"massive:model:spot:{symbol}")
    spot = float(json.loads(spot_raw).get("value")) if spot_raw else None

    await r.aclose()
    return heatmap_model, calls_model, puts_model, spot

def plot_side_by_side(heatmap_model, calls_model, puts_model, symbol, strategy, side, spot=None):
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
        for i, strike in enumerate(strikes):
            tile = tiles.get(str(int(strike)), {})
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

        # Dynamic widths - collect from ALL strikes, not just the first
        all_widths = set()
        for strike_data in tiles.values():
            for w in strike_data.keys():
                if w.isdigit():
                    all_widths.add(int(w))
        widths = sorted(all_widths)
        if not widths:
            widths = [20, 25, 30, 35, 40, 45, 50]

        strikes = sorted([float(s) for s in tiles.keys()], reverse=True)
        grid = np.full((len(strikes), len(widths)), np.nan)
        for i, strike in enumerate(strikes):
            strike_tiles = tiles.get(str(int(strike)), {})
            for j, w in enumerate(widths):
                w_str = str(w)
                val = strike_tiles.get(w_str)
                if isinstance(val, dict):
                    val = val.get("value")
                if val is not None:
                    grid[i, j] = val

        title = f'Convexity Heatmap\n{symbol} - {strategy.capitalize()} - {side.capitalize()}'

    # GEX - use same strikes as heatmap for alignment
    gex_values = []
    expirations = calls_model.get("expirations", {})
    if expirations:
        exp_key = next(iter(expirations))
        exp_data = expirations[exp_key]
        put_data = puts_model.get("expirations", {}).get(exp_key, {})
        # Build GEX values aligned with heatmap strikes
        for strike in strikes:
            s_str = str(int(strike))
            call_gex = exp_data.get(s_str, 0)
            put_gex = put_data.get(s_str, 0)
            gex_values.append(call_gex - put_gex)
        gex_title = exp_key
    else:
        gex_title = "N/A"
        gex_values = [0] * len(strikes)

    fig = plt.figure(figsize=(16, 10), facecolor='black')
    gs = fig.add_gridspec(1, 2, width_ratios=[1, 3], wspace=0.05)

    ax_gex = fig.add_subplot(gs[0])
    ax_gex.set_facecolor('black')
    if gex_values and strikes:
        # Use indices for y-axis to match heatmap alignment
        y_positions = np.arange(len(strikes))
        colors = ['green' if v > 0 else 'red' for v in gex_values]
        ax_gex.barh(y_positions, gex_values, color=colors)
        ax_gex.set_yticks(y_positions)
        ax_gex.set_yticklabels([int(s) for s in strikes], color='white')
        ax_gex.invert_yaxis()  # Match heatmap: higher strikes at top
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

    if spot and strikes and min(strikes) <= spot <= max(strikes):
        # Find index of strike closest to spot (strikes are descending)
        spot_idx = min(range(len(strikes)), key=lambda i: abs(strikes[i] - spot))
        ax_heat.axhline(spot_idx, color='yellow', linewidth=2, linestyle='--')
        ax_gex.axhline(spot_idx, color='yellow', linewidth=2, linestyle='--')
        ax_heat.text(len(widths), spot_idx, f' Spot {spot:.2f}', color='yellow', va='center', ha='left', fontweight='bold')

    plt.suptitle(f'{symbol} - {strategy.capitalize()} - {"Call/Put" if strategy == "single" else side.capitalize()}', color='white')
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    outfile = f"heatmap_gex_{timestamp}.png"
    plt.savefig(outfile, dpi=150, bbox_inches='tight', facecolor='black')
    print(f"Plot saved as {outfile}")

def transform_tiles_to_legacy(model, strategy, side, dte_filter=None):
    """
    Transform new tile-key format to legacy nested format for plotting.

    New format: tiles["butterfly:0:25:6000"] = {dte, strike, width, call: {...}, put: {...}}
    Legacy format: model["butterfly_call"]["6000"]["25"] = {"value": debit}

    Also handles replay delta format: {"ts": ..., "delta": {...}}

    Args:
        model: The model data
        strategy: "butterfly", "vertical", or "single"
        side: "call" or "put"
        dte_filter: If specified, only include tiles with this DTE
    """
    if not model:
        return None

    # Handle replay delta format
    if "delta" in model and "tiles" not in model:
        tiles = model.get("delta", {})
    elif "tiles" in model:
        tiles = model.get("tiles", {})
    else:
        # Model might be tiles directly (from replay extraction)
        tiles = model
    result = {}

    for tile_key, tile in tiles.items():
        parts = tile_key.split(":")
        if len(parts) != 4:
            continue

        tile_strategy, dte, width, strike = parts

        if tile_strategy != strategy:
            continue

        # Filter by DTE if specified
        if dte_filter is not None and int(dte) != dte_filter:
            continue

        # Get the value for the requested side
        side_data = tile.get(side, {})

        # For singles, use "mid" instead of "debit"
        if strategy == "single":
            value = side_data.get("mid")
        else:
            value = side_data.get("debit")

        if value is None:
            continue

        strike_str = strike
        width_str = width

        result.setdefault(strike_str, {})[width_str] = {"value": value}

    return {f"{strategy}_{side}": result} if result else None


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbol', default=DEFAULT_SYMBOL)
    parser.add_argument('--strategy', default=DEFAULT_STRATEGY, choices=['butterfly', 'vertical', 'single'])
    parser.add_argument('--side', default=DEFAULT_SIDE, choices=['call', 'put'])
    parser.add_argument('--dte', type=int, default=0, help='Days to expiration filter (default: 0)')
    parser.add_argument('--input', help='Path to JSON file with model data (optional, otherwise fetches from Redis)')
    args = parser.parse_args()

    if args.input:
        # Load heatmap from file
        with open(args.input, 'r') as f:
            raw_model = json.load(f)
        # Transform new format to legacy format
        heatmap = transform_tiles_to_legacy(raw_model, args.strategy, args.side, args.dte)
        # Still fetch GEX and spot from Redis
        _, calls, puts, spot = await fetch_models(args.symbol)
    else:
        # Fetch from Redis
        heatmap, calls, puts, spot = await fetch_models(args.symbol)
        # Transform if new format detected
        if heatmap and "tiles" in heatmap:
            heatmap = transform_tiles_to_legacy(heatmap, args.strategy, args.side, args.dte)

    plot_side_by_side(heatmap, calls, puts, args.symbol, args.strategy, args.side, spot)

if __name__ == "__main__":
    asyncio.run(main())