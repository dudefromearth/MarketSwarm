#!/usr/bin/env python3

import asyncio
from redis.asyncio import Redis
import matplotlib.pyplot as plt
import argparse
from datetime import datetime
import time
import json

async def fetch_analytics():
    r = Redis.from_url("redis://127.0.0.1:6380", decode_responses=True)
    analytics = await r.hgetall("massive:model:analytics")
    await r.aclose()
    return analytics

def save_json(analytics, filename):
    with open(filename, 'w') as f:
        json.dump(analytics, f, indent=2)
    print(f"Saved JSON to {filename}")

def plot_dashboard(analytics):
    # Group by builder
    builders = {"heatmap": {}, "gex": {}, "global": {}}
    for k, v in analytics.items():
        if ':' in k:
            builder, metric = k.split(':', 1)
            builders.setdefault(builder, {})[metric] = int(v or 0)
        else:
            builders["global"][k] = int(v or 0)

    # Extract metrics
    labels = []
    runs = []
    totals = []
    latency_last = []
    latency_avg = []
    colors = []

    for builder, metrics in builders.items():
        if builder == "global":
            continue
        labels.append(builder.capitalize())
        runs.append(metrics.get("runs", 0))
        totals.append(metrics.get("tiles_total", metrics.get("levels_total", 0)))
        latency_last.append(metrics.get("latency_last_ms", 0))
        latency_avg.append(metrics.get("latency_avg_ms", 0))
        colors.append('blue' if builder == "heatmap" else 'green')

    fig, axs = plt.subplots(3, 1, figsize=(12, 12))

    # Bar chart
    x = range(len(labels))
    axs[0].bar([i - 0.3 for i in x], runs, width=0.2, label='Runs', color=colors, alpha=0.8)
    axs[0].bar([i - 0.1 for i in x], totals, width=0.2, label='Tiles/Levels', color=colors, alpha=0.6)
    axs[0].bar([i + 0.1 for i in x], latency_last, width=0.2, label='Latency Last (ms)', color=colors, alpha=0.7)
    axs[0].bar([i + 0.3 for i in x], latency_avg, width=0.2, label='Latency Avg (ms)', color=colors, alpha=0.5)
    axs[0].set_xticks(x)
    axs[0].set_xticklabels(labels)
    axs[0].set_title('Model Builders Performance')
    axs[0].set_ylabel('Count / ms')
    axs[0].legend()

    # Placeholder trend (extend with ZSET)
    times = [datetime.now() for _ in range(len(labels))]
    axs[1].plot(times, runs, marker='o', label='Runs')
    axs[1].plot(times, totals, marker='o', label='Tiles/Levels')
    axs[1].set_title('Trend Over Time (Placeholder)')
    axs[1].legend()

    # Pie (work distribution)
    pie_values = [runs[i] + totals[i] for i in range(len(runs))]
    axs[2].pie(pie_values, labels=labels, autopct='%1.1f%%')
    axs[2].set_title('Work Distribution')

    plt.tight_layout()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    outfile = f"model_analytics_{timestamp}.png"
    plt.savefig(outfile)
    print(f"Dashboard saved as {outfile}")

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', choices=['terminal', 'json', 'both'], default='terminal')
    parser.add_argument('--file', type=str, default=None)
    args = parser.parse_args()

    analytics = await fetch_analytics()
    print("Fetched Analytics:", analytics)

    if args.output in ['terminal', 'both']:
        plot_dashboard(analytics)

    if args.output in ['json', 'both']:
        filename = args.file or f"analytics_{int(time.time())}.json"
        save_json(analytics, filename)

if __name__ == "__main__":
    asyncio.run(main())