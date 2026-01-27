#!/usr/bin/env python3

import asyncio
from redis.asyncio import Redis
import json
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime
import argparse

DEFAULT_SYMBOL = "I:SPX"

async def fetch_gex(symbol):
    r = Redis.from_url("redis://127.0.0.1:6380", decode_responses=True)

    calls_raw = await r.get(f"massive:gex:model:{symbol}:calls")
    puts_raw = await r.get(f"massive:gex:model:{symbol}:puts")
    calls_model = json.loads(calls_raw) if calls_raw else {}
    puts_model = json.loads(puts_raw) if puts_raw else {}

    await r.aclose()
    return calls_model, puts_model

def plot_gex(calls_model, puts_model, symbol):
    call_levels = calls_model.get('levels', {})
    put_levels = puts_model.get('levels', {})

    # Strikes from GEX levels
    strikes = sorted(set(float(k) for k in call_levels) | set(float(k) for k in put_levels), reverse=True)

    gex = np.zeros(len(strikes))
    for i, s in enumerate(strikes):
        call = call_levels.get(str(s), 0)
        put = put_levels.get(str(s), 0)
        gex[i] = call - put

    fig, ax = plt.subplots(figsize=(10, 12), facecolor='black')
    colors = ['green' if v > 0 else 'red' if v < 0 else 'gray' for v in gex]
    ax.barh(range(len(strikes)), gex, color=colors)
    ax.set_yticks(range(len(strikes)))
    ax.set_yticklabels([f"{s:.0f}" for s in strikes], color='white', fontsize=8)
    ax.set_xlabel('Gamma Exposure', color='white')
    ax.set_title(f'Gamma Exposure\n{symbol}', color='white')
    ax.axvline(0, color='white', linewidth=0.5)
    ax.tick_params(axis='x', colors='white')
    ax.set_facecolor('black')

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    outfile = f"gex_{symbol.replace(':', '')}_{timestamp}.png"
    plt.savefig(outfile, dpi=150, bbox_inches='tight', facecolor='black')
    print(f"GEX plot saved as {outfile}")

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbol', default=DEFAULT_SYMBOL)
    args = parser.parse_args()

    calls, puts = await fetch_gex(args.symbol)
    plot_gex(calls, puts, args.symbol)

if __name__ == "__main__":
    asyncio.run(main())