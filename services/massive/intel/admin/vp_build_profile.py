#!/usr/bin/env python3
"""
vp_build_profile.py

Build a synthetic SPX/NDX volume profile from 1-min ETF bars and
store it in Redis.

Input JSON (from vp_download_history.py):

{
  "ticker": "SPY",
  "start": "YYYY-MM-DD",
  "end": "YYYY-MM-DD",
  "bars": [ { "o":..., "h":..., "l":..., "c":..., "v":..., "t":... }, ... ]
}

Output keys:

  SYSTEM_REDIS:
    massive:volume_profile          → full schema (same shape as original script)

  MARKET_REDIS (optional):
    sse:volume-profile              → published light payload:
      { "symbol": "SPX", "mode": "raw|tv", "buckets": { price: vol, ... } }

Usage:

  python vp_build_profile.py \
    --ticker SPY \
    --file ./data/vp/SPY_1min_YYYY-MM-DD_to_YYYY-MM-DD.json \
    --publish raw

  # With visualization for structural analysis:
  python vp_build_profile.py \
    --ticker SPY \
    --file ./data/vp/SPY_1min.json \
    --publish tv \
    --visualize
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, UTC
from typing import Any, Dict, List

import redis

# AI analysis integration
try:
    from vp_ai_analysis import (
        analyze_chart_with_claude,
        print_ai_analysis,
        compare_structures,
        print_comparison,
    )
    HAS_AI_ANALYSIS = True
except ImportError:
    HAS_AI_ANALYSIS = False


INSTRUMENTS: Dict[str, Dict[str, Any]] = {
    "SPY": {"synthetic": "SPX", "multiplier": 10},
    "QQQ": {"synthetic": "NDX", "multiplier": 4},
}

BIN_SIZE = 1

# Standardized price range for SPX volume profile
SPX_MIN_PRICE = 2000
SPX_MAX_PRICE = 7000

SYSTEM_REDIS_URL = os.getenv("SYSTEM_REDIS_URL", "redis://127.0.0.1:6379")
MARKET_REDIS_URL = os.getenv("MARKET_REDIS_URL", "redis://127.0.0.1:6380")
SYSTEM_KEY = "massive:volume_profile"
MARKET_CHANNEL = "sse:volume-profile"


def log(stage: str, emoji: str, msg: str) -> None:
    print(f"[vp_build|{stage}]{emoji} {msg}")


def rds_system() -> redis.Redis:
    return redis.Redis.from_url(SYSTEM_REDIS_URL, decode_responses=True)


def rds_market() -> redis.Redis:
    return redis.Redis.from_url(MARKET_REDIS_URL, decode_responses=True)


def accumulate_raw(
    bins_raw: Dict[int, float],
    price: float | None,
    vol: float | None,
    multiplier: int,
) -> None:
    """RAW mode: Volume at close price."""
    if price is None or vol is None:
        return
    spx = int(round(price * multiplier))
    bins_raw[spx] = bins_raw.get(spx, 0.0) + float(vol)


def accumulate_tv(
    bins_tv: Dict[int, float],
    low: float | None,
    high: float | None,
    vol: float | None,
    multiplier: int,
    microbins: int = 30,
) -> None:
    """TV mode: Volume distributed across bar's high-low range using microbins."""
    if low is None or high is None or vol is None:
        return
    if high <= low:
        return

    step = (high - low) / microbins
    vol_per = vol / microbins

    for i in range(microbins):
        spy_price = low + i * step
        spx = int(round(spy_price * multiplier))
        bins_tv[spx] = bins_tv.get(spx, 0.0) + vol_per


def create_standardized_bins(buckets: Dict[int, float]) -> Dict[str, float]:
    """
    Create standardized bins from SPX_MIN_PRICE to SPX_MAX_PRICE.
    Each bin represents $1 price level with its volume.
    Bins outside the data range are zero-filled.
    """
    standardized = {}
    for price in range(SPX_MIN_PRICE, SPX_MAX_PRICE + 1):
        volume = buckets.get(price, 0.0)
        standardized[str(price)] = float(volume)
    return standardized


def auto_detect_structures(
    bins: Dict[int, float],
    top_n_nodes: int = 10,
    min_crevasse_width: int = 5,
    price_min: int | None = None,
    price_max: int | None = None,
) -> Dict[str, Any]:
    """
    Automatically detect structural elements from volume profile.

    Args:
        bins: Price -> Volume mapping (TV smoothed preferred)
        top_n_nodes: Number of top volume nodes to detect
        min_crevasse_width: Minimum width (in price points) for crevasse detection
        price_min: Optional minimum price to filter detection range
        price_max: Optional maximum price to filter detection range

    Returns:
        {
            "volume_nodes": [price1, price2, ...],  # Top N volume peaks
            "volume_wells": [price1, price2, ...],  # Local minima between peaks
            "crevasses": [[start, end], ...],       # Extended low-volume regions
        }
    """
    if not bins:
        return {"volume_nodes": [], "volume_wells": [], "crevasses": []}

    # Filter bins by price range if specified
    if price_min is not None or price_max is not None:
        filtered_bins = {}
        for p, v in bins.items():
            if price_min is not None and p < price_min:
                continue
            if price_max is not None and p > price_max:
                continue
            filtered_bins[p] = v
        bins = filtered_bins
        if price_min and price_max:
            log("struct", "🔍", f"Filtering detection to price range: ${price_min:,} - ${price_max:,}")

    # Get prices with actual volume, sorted by price
    prices_with_vol = sorted([(p, v) for p, v in bins.items() if v > 0], key=lambda x: x[0])

    if not prices_with_vol:
        return {"volume_nodes": [], "volume_wells": [], "crevasses": []}

    # Calculate volume statistics
    volumes = [v for _, v in prices_with_vol]
    max_vol = max(volumes)
    mean_vol = sum(volumes) / len(volumes)
    price_list = [p for p, _ in prices_with_vol]
    vol_list = [v for _, v in prices_with_vol]

    # --- Volume Nodes: Find TRANSITION POINTS where volume changes significantly ---
    # These are the boundaries between high and low volume areas:
    # - Where volume starts rising (bottom edge of a cluster)
    # - Where volume drops off (top edge before a valley)
    # - Both sides of deep cracks/crevasses

    # Light smoothing to reduce noise but preserve edges
    smoothed = []
    window = 2
    for i in range(len(vol_list)):
        start = max(0, i - window)
        end = min(len(vol_list), i + window + 1)
        smoothed.append(sum(vol_list[start:end]) / (end - start))

    # Calculate the gradient (rate of change) at each point
    gradients = []
    for i in range(1, len(smoothed) - 1):
        # Gradient = difference between neighbors
        grad = smoothed[i + 1] - smoothed[i - 1]
        gradients.append((price_list[i], grad, smoothed[i]))

    # Find significant gradient changes (transitions)
    # A transition occurs where the gradient is large (steep change in volume)
    edge_candidates = []
    grad_values = [abs(g[1]) for g in gradients]
    if grad_values:
        avg_grad = sum(grad_values) / len(grad_values)
        grad_threshold = avg_grad * 0.8  # Lower threshold to catch more transitions

        for i, (price, grad, vol) in enumerate(gradients):
            abs_grad = abs(grad)
            if abs_grad > grad_threshold:
                # Score by gradient magnitude relative to max volume
                score = abs_grad / max_vol if max_vol > 0 else 0
                edge_candidates.append((price, vol, score, 'rising' if grad > 0 else 'falling'))

    # Also find inflection points (where gradient changes direction significantly)
    for i in range(1, len(gradients) - 1):
        prev_grad = gradients[i - 1][1]
        curr_grad = gradients[i][1]

        # Inflection: gradient changes sign or magnitude changes sharply
        if (prev_grad > 0 and curr_grad < 0) or (prev_grad < 0 and curr_grad > 0):
            # Sign change - this is a local max or min
            price = gradients[i][0]
            vol = gradients[i][2]
            score = abs(prev_grad - curr_grad) / max_vol if max_vol > 0 else 0
            if score > 0.002:  # Lower minimum significance
                edge_candidates.append((price, vol, score * 2, 'inflection'))  # Boost inflection points

    # Sort by score and take top N, with minimum spacing
    edge_candidates.sort(key=lambda x: x[2], reverse=True)

    volume_nodes = []
    min_spacing = 5  # Reduced spacing to catch more edges
    for price, vol, score, edge_type in edge_candidates:
        too_close = any(abs(price - existing) < min_spacing for existing in volume_nodes)
        if not too_close:
            volume_nodes.append(price)
            if len(volume_nodes) >= top_n_nodes:
                break

    volume_nodes.sort()  # Sort by price for display

    # --- Volume Wells: Local minima (thin areas) between ledges ---
    volume_wells = []
    threshold = mean_vol * 0.3  # Wells are significantly below average

    # Find local minima
    for i in range(2, len(smoothed) - 2):
        current = smoothed[i]
        if current < smoothed[i-1] and current < smoothed[i+1]:
            if current < threshold:
                price = price_list[i]
                # Not too close to existing wells
                too_close = any(abs(price - existing) < 15 for existing in volume_wells)
                if not too_close:
                    volume_wells.append(price)

    volume_wells.sort()
    volume_wells = volume_wells[:10]  # Limit to top 10

    # --- Crevasses: Deep cracks in the volume profile ---
    # Find areas where volume drops sharply - these are the "air pockets" between volume clusters
    crevasses = []

    # Method 1: Find valleys - local minima that are significantly below neighbors
    for i in range(5, len(smoothed) - 5):
        current = smoothed[i]

        # Look at volume on both sides
        left_max = max(smoothed[max(0, i-10):i]) if i > 0 else current
        right_max = max(smoothed[i+1:min(len(smoothed), i+11)]) if i < len(smoothed)-1 else current

        # It's a crevasse if current is much lower than both sides
        left_ratio = current / left_max if left_max > 0 else 1
        right_ratio = current / right_max if right_max > 0 else 1

        # Must be below 50% of BOTH sides to be a true crack
        if left_ratio < 0.5 and right_ratio < 0.5:
            price = price_list[i]
            depth = 1 - max(left_ratio, right_ratio)  # How deep is the crack

            # Check if this extends an existing crevasse
            if crevasses and price - crevasses[-1][1] <= 5:
                crevasses[-1][1] = price
                crevasses[-1].append(depth) if len(crevasses[-1]) == 2 else None
            else:
                crevasses.append([price, price])

    # Method 2: Find extended low-volume regions
    low_threshold = mean_vol * 0.35  # More sensitive threshold
    in_crevasse = False
    crevasse_start = 0

    for i, (price, vol) in enumerate(prices_with_vol):
        if vol < low_threshold:
            if not in_crevasse:
                in_crevasse = True
                crevasse_start = price
        else:
            if in_crevasse:
                crevasse_end = prices_with_vol[i-1][0] if i > 0 else price
                width = crevasse_end - crevasse_start
                if width >= 2:  # Lower minimum width
                    # Check if overlaps with existing crevasse
                    merged = False
                    for j, existing in enumerate(crevasses):
                        cs, ce = existing[0], existing[1]
                        if not (crevasse_end < cs - 3 or crevasse_start > ce + 3):
                            crevasses[j] = [min(cs, crevasse_start), max(ce, crevasse_end)]
                            merged = True
                            break
                    if not merged:
                        crevasses.append([crevasse_start, crevasse_end])
                in_crevasse = False

    # Handle crevasse at end
    if in_crevasse:
        crevasse_end = prices_with_vol[-1][0]
        width = crevasse_end - crevasse_start
        if width >= 2:
            crevasses.append([crevasse_start, crevasse_end])

    # Clean up crevasses - keep only [start, end] pairs
    crevasses = [[c[0], c[1]] for c in crevasses]

    # Sort crevasses by start price
    crevasses.sort(key=lambda x: x[0])

    log("struct", "🔍", f"Auto-detected: {len(volume_nodes)} nodes, {len(volume_wells)} wells, {len(crevasses)} crevasses")

    return {
        "volume_nodes": volume_nodes,
        "volume_wells": volume_wells,
        "crevasses": crevasses,
    }


def save_to_system_redis(obj: Dict[str, Any]) -> None:
    out = dict(obj)

    # Create standardized bins from 2000-7000
    raw_standardized = create_standardized_bins(obj.get("buckets_raw", {}))
    tv_standardized = create_standardized_bins(obj.get("buckets_tv", {}))

    out["buckets_raw"] = raw_standardized
    out["buckets_tv"] = tv_standardized
    out["min_price"] = SPX_MIN_PRICE
    out["max_price"] = SPX_MAX_PRICE
    out["bin_count"] = SPX_MAX_PRICE - SPX_MIN_PRICE + 1

    rds_system().set(SYSTEM_KEY, json.dumps(out))
    log("redis", "💾", f"Wrote base profile to SYSTEM_REDIS ({SYSTEM_KEY})")
    log("redis", "💾", f"  Standardized bins: {out['bin_count']} (${SPX_MIN_PRICE}-${SPX_MAX_PRICE})")


def publish_to_market(obj: Dict[str, Any]) -> None:
    rds_market().publish(MARKET_CHANNEL, json.dumps(obj))
    log("redis", "📡", f"Published profile to MARKET_REDIS ({MARKET_CHANNEL})")


def generate_ai_chart(
    bins_tv: Dict[int, float],
    synthetic: str,
    save_path: str,
    price_min: int | None = None,
    price_max: int | None = None,
) -> str | None:
    """
    Generate a focused, high-detail chart for AI visual analysis.
    Shows just the volume profile in a single panel, zoomed to the price range.
    """
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        log("viz", "⚠️", "matplotlib not available")
        return None

    if not bins_tv:
        log("viz", "⚠️", "No TV data for AI chart")
        return None

    # Filter to price range
    if price_min is not None or price_max is not None:
        filtered_bins = {}
        for p, v in bins_tv.items():
            if price_min is not None and p < price_min:
                continue
            if price_max is not None and p > price_max:
                continue
            filtered_bins[p] = v
        bins_tv = filtered_bins

    if not bins_tv:
        log("viz", "⚠️", "No data in price range")
        return None

    # Sort by price
    prices = sorted(bins_tv.keys())
    volumes = [bins_tv[p] for p in prices]
    max_vol = max(volumes) if volumes else 1
    norm_volumes = [v / max_vol for v in volumes]

    # Create a large, detailed chart
    fig, ax = plt.subplots(figsize=(20, 12))

    # Horizontal bar chart (price on Y-axis, volume on X-axis)
    ax.barh(prices, norm_volumes, height=1, color='#3b82f6', alpha=0.8)

    ax.set_xlabel('Normalized Volume', fontsize=12)
    ax.set_ylabel('Price', fontsize=12)
    ax.set_title(f'{synthetic} Volume Profile - AI Analysis Range', fontsize=14)
    ax.grid(True, alpha=0.3, axis='x')

    # Add price labels on Y-axis at regular intervals
    price_range = max(prices) - min(prices)
    tick_interval = max(10, price_range // 30)  # Aim for ~30 ticks
    ax.set_yticks([p for p in prices if p % tick_interval == 0])

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        log("viz", "📊", f"AI analysis chart saved to: {save_path}")
        plt.close()
        return save_path
    else:
        plt.show()
        return None


def visualize_profile(
    bins_raw: Dict[int, float],
    bins_tv: Dict[int, float],
    synthetic: str,
    save_path: str | None = None,
    structures: Dict[str, Any] | None = None,
) -> None:
    """
    Visualize both RAW and TV smoothed volume profiles side by side.
    Optionally overlay user-defined structures (Volume Nodes, Wells, Crevasses).
    Opens a matplotlib chart for interactive exploration.
    """
    try:
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        log("viz", "⚠️", "matplotlib not available. Install with: pip install matplotlib")
        return

    if not bins_raw and not bins_tv:
        log("viz", "⚠️", "No data to visualize")
        return

    # Use TV for structural analysis, but show both
    bins_for_analysis = bins_tv if bins_tv else bins_raw

    # Get all prices (union of both)
    all_prices = sorted(set(bins_raw.keys()) | set(bins_tv.keys()))

    # Filter to prices with actual volume
    prices_with_vol = [p for p in all_prices if bins_raw.get(p, 0) > 0 or bins_tv.get(p, 0) > 0]

    if not prices_with_vol:
        log("viz", "⚠️", "No volume data to visualize")
        return

    # Get volumes for both
    raw_volumes = [bins_raw.get(p, 0) for p in prices_with_vol]
    tv_volumes = [bins_tv.get(p, 0) for p in prices_with_vol]

    # Normalize for display (use same scale for comparison)
    max_vol = max(max(raw_volumes) if raw_volumes else 1, max(tv_volumes) if tv_volumes else 1)
    norm_raw = [v / max_vol for v in raw_volumes]
    norm_tv = [v / max_vol for v in tv_volumes]

    # Create figure with 2x2 subplots
    fig, axes = plt.subplots(2, 2, figsize=(18, 14))
    fig.suptitle(f"{synthetic} Volume Profile - RAW vs TV Smoothed (10 Year)", fontsize=16)

    # Top Left: RAW profile
    ax_raw = axes[0, 0]
    ax_raw.barh(prices_with_vol, norm_raw, height=1, color='#ef4444', alpha=0.7)
    ax_raw.set_xlabel('Normalized Volume')
    ax_raw.set_ylabel('Price')
    ax_raw.set_title('RAW (Close Price Accumulation)')
    ax_raw.grid(True, alpha=0.3)

    # Top Right: TV Smoothed profile
    ax_tv = axes[0, 1]
    ax_tv.barh(prices_with_vol, norm_tv, height=1, color='#9333ea', alpha=0.7)
    ax_tv.set_xlabel('Normalized Volume')
    ax_tv.set_ylabel('Price')
    ax_tv.set_title('TV Smoothed (Microbin Distribution)')
    ax_tv.grid(True, alpha=0.3)

    # Bottom Left: Top 20 RAW Volume Nodes
    ax_raw_top = axes[1, 0]
    sorted_raw = sorted(bins_raw.items(), key=lambda x: x[1], reverse=True)[:20]
    if sorted_raw:
        top_prices_raw = [p for p, v in sorted_raw]
        top_vols_raw = [v / max_vol for p, v in sorted_raw]
        colors_raw = ['#dc2626' if i < 5 else '#f97316' if i < 10 else '#fbbf24' for i in range(len(top_prices_raw))]
        ax_raw_top.barh(range(len(top_prices_raw)), top_vols_raw, color=colors_raw, alpha=0.8)
        ax_raw_top.set_yticks(range(len(top_prices_raw)))
        ax_raw_top.set_yticklabels([f"${p:,}" for p in top_prices_raw])
        ax_raw_top.set_xlabel('Normalized Volume')
        ax_raw_top.set_title('Top 20 RAW Volume Nodes')
        ax_raw_top.invert_yaxis()

    # Bottom Right: Top 20 TV Volume Nodes
    ax_tv_top = axes[1, 1]
    sorted_tv = sorted(bins_tv.items(), key=lambda x: x[1], reverse=True)[:20]
    if sorted_tv:
        top_prices_tv = [p for p, v in sorted_tv]
        top_vols_tv = [v / max_vol for p, v in sorted_tv]
        colors_tv = ['#22c55e' if i < 5 else '#facc15' if i < 10 else '#9333ea' for i in range(len(top_prices_tv))]
        ax_tv_top.barh(range(len(top_prices_tv)), top_vols_tv, color=colors_tv, alpha=0.8)
        ax_tv_top.set_yticks(range(len(top_prices_tv)))
        ax_tv_top.set_yticklabels([f"${p:,}" for p in top_prices_tv])
        ax_tv_top.set_xlabel('Normalized Volume')
        ax_tv_top.set_title('Top 20 TV Volume Nodes')
        ax_tv_top.invert_yaxis()

    # Add legends
    from matplotlib.patches import Patch
    legend_raw = [
        Patch(facecolor='#dc2626', label='Top 5'),
        Patch(facecolor='#f97316', label='Top 6-10'),
        Patch(facecolor='#fbbf24', label='Top 11-20'),
    ]
    ax_raw_top.legend(handles=legend_raw, loc='lower right', fontsize=8)

    legend_tv = [
        Patch(facecolor='#22c55e', label='Top 5'),
        Patch(facecolor='#facc15', label='Top 6-10'),
        Patch(facecolor='#9333ea', label='Top 11-20'),
    ]
    ax_tv_top.legend(handles=legend_tv, loc='lower right', fontsize=8)

    # Overlay user-defined structures on profile charts
    if structures:
        volume_nodes = structures.get("volume_nodes", [])
        volume_wells = structures.get("volume_wells", [])
        crevasses = structures.get("crevasses", [])

        # Apply to both RAW and TV profile charts
        for ax in [ax_raw, ax_tv]:
            # Volume Nodes - green horizontal lines
            for price in volume_nodes:
                ax.axhline(y=price, color='#22c55e', linewidth=2, linestyle='-', alpha=0.9)
                ax.annotate(f'Node ${price:,}', xy=(0.95, price), xycoords=('axes fraction', 'data'),
                           fontsize=7, color='#22c55e', ha='right', va='center',
                           bbox=dict(boxstyle='round,pad=0.2', facecolor='black', alpha=0.7))

            # Volume Wells - yellow horizontal lines
            for price in volume_wells:
                ax.axhline(y=price, color='#facc15', linewidth=2, linestyle='--', alpha=0.9)
                ax.annotate(f'Well ${price:,}', xy=(0.95, price), xycoords=('axes fraction', 'data'),
                           fontsize=7, color='#facc15', ha='right', va='center',
                           bbox=dict(boxstyle='round,pad=0.2', facecolor='black', alpha=0.7))

            # Crevasses - red shaded regions
            for crevasse in crevasses:
                if len(crevasse) == 2:
                    start, end = crevasse
                    ax.axhspan(start, end, color='#ef4444', alpha=0.3)
                    mid = (start + end) / 2
                    ax.annotate(f'Crevasse', xy=(0.5, mid), xycoords=('axes fraction', 'data'),
                               fontsize=7, color='#ef4444', ha='center', va='center',
                               bbox=dict(boxstyle='round,pad=0.2', facecolor='black', alpha=0.7))

        # Add structure legend to TV chart
        structure_legend = []
        if volume_nodes:
            structure_legend.append(Patch(facecolor='#22c55e', label=f'Volume Nodes ({len(volume_nodes)})'))
        if volume_wells:
            structure_legend.append(Patch(facecolor='#facc15', label=f'Volume Wells ({len(volume_wells)})'))
        if crevasses:
            structure_legend.append(Patch(facecolor='#ef4444', alpha=0.3, label=f'Crevasses ({len(crevasses)})'))

        if structure_legend:
            ax_tv.legend(handles=structure_legend, loc='upper right', fontsize=8)

    plt.tight_layout()

    # Print structural analysis hints (using TV)
    print("\n" + "="*70)
    print("STRUCTURAL ANALYSIS - RAW vs TV COMPARISON")
    print("="*70)

    print("\nTop 5 RAW Volume Nodes:")
    for i, (p, v) in enumerate(sorted_raw[:5]):
        print(f"  {i+1}. ${p:,} - {v/max_vol*100:.1f}%")

    print("\nTop 5 TV Volume Nodes:")
    for i, (p, v) in enumerate(sorted_tv[:5]):
        print(f"  {i+1}. ${p:,} - {v/max_vol*100:.1f}%")

    # Find differences
    raw_top5 = set(p for p, v in sorted_raw[:5])
    tv_top5 = set(p for p, v in sorted_tv[:5])
    only_raw = raw_top5 - tv_top5
    only_tv = tv_top5 - raw_top5

    if only_raw or only_tv:
        print("\nDifferences in Top 5:")
        if only_raw:
            print(f"  Only in RAW: {', '.join(f'${p:,}' for p in sorted(only_raw))}")
        if only_tv:
            print(f"  Only in TV:  {', '.join(f'${p:,}' for p in sorted(only_tv))}")

    # Low volume regions (Crevasses) using TV
    print("\nCrevasses (TV-based, bottom 10% volume):")
    threshold = max_vol * 0.1
    low_vol_prices = sorted([p for p, v in bins_tv.items() if 0 < v < threshold])

    if low_vol_prices:
        regions = []
        start = low_vol_prices[0]
        prev = start
        for p in low_vol_prices[1:]:
            if p - prev > 2:
                if prev - start >= 3:
                    regions.append((start, prev))
                start = p
            prev = p
        if prev - start >= 3:
            regions.append((start, prev))

        for s, e in regions[:5]:
            print(f"  ${s:,} to ${e:,} (${e-s} range)")
    else:
        print("  No significant low-volume regions")

    print("="*70)

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"\nChart saved to: {save_path}")
        plt.close()
    else:
        print("\nClose the chart window to continue...")
        plt.show()


def interactive_structure_editor(
    bins: Dict[int, float],
    synthetic: str,
) -> Dict[str, Any]:
    """
    Interactive editor for structural analysis.
    Allows user to define Volume Nodes, Wells, and Crevasses.
    """
    print("\n" + "="*60)
    print("INTERACTIVE STRUCTURAL ANALYSIS")
    print("="*60)
    print("\nYou can now define structural elements for the AI to learn from.")
    print("Enter prices separated by commas, or press Enter to skip.\n")

    structures = {
        "volume_nodes": [],
        "volume_wells": [],
        "crevasses": [],
    }

    # Volume Nodes
    nodes_input = input("Volume Nodes (prices, e.g., 6000,6050,6100): ").strip()
    if nodes_input:
        try:
            structures["volume_nodes"] = [int(p.strip()) for p in nodes_input.split(",")]
            print(f"  Added {len(structures['volume_nodes'])} Volume Nodes")
        except ValueError:
            print("  Invalid input, skipping")

    # Volume Wells
    wells_input = input("Volume Wells (prices, e.g., 5980,6025): ").strip()
    if wells_input:
        try:
            structures["volume_wells"] = [int(p.strip()) for p in wells_input.split(",")]
            print(f"  Added {len(structures['volume_wells'])} Volume Wells")
        except ValueError:
            print("  Invalid input, skipping")

    # Crevasses (ranges)
    crevasses_input = input("Crevasses (ranges, e.g., 5950-5970,6080-6090): ").strip()
    if crevasses_input:
        try:
            for r in crevasses_input.split(","):
                start, end = r.strip().split("-")
                structures["crevasses"].append([int(start), int(end)])
            print(f"  Added {len(structures['crevasses'])} Crevasses")
        except ValueError:
            print("  Invalid input, skipping")

    return structures


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()

    ap.add_argument(
        "--ticker",
        type=str,
        required=True,
        help="Underlying ETF used for profile (SPY, QQQ)",
    )
    ap.add_argument(
        "--file",
        type=str,
        required=True,
        help="JSON file produced by vp_download_history.py",
    )
    ap.add_argument(
        "--publish",
        type=str,
        default="raw",
        choices=["raw", "tv", "both", "none"],
        help="How to publish to MARKET_REDIS",
    )
    ap.add_argument(
        "--visualize",
        action="store_true",
        help="Open visualization for structural analysis",
    )
    ap.add_argument(
        "--interactive",
        action="store_true",
        help="Enable interactive structure editor after visualization",
    )
    ap.add_argument(
        "--save-chart",
        type=str,
        default=None,
        help="Save chart to file instead of displaying (e.g., chart.png)",
    )
    ap.add_argument(
        "--ai-analyze",
        action="store_true",
        help="Run AI analysis on the chart using Claude Vision",
    )
    ap.add_argument(
        "--ai-model",
        type=str,
        default="claude-sonnet-4-20250514",
        help="Claude model for AI analysis (default: claude-sonnet-4-20250514)",
    )
    ap.add_argument(
        "--top-nodes",
        type=int,
        default=10,
        help="Number of top volume nodes to auto-detect (default: 10)",
    )
    ap.add_argument(
        "--price-min",
        type=int,
        default=None,
        help="Minimum price for structure detection (e.g., 5800)",
    )
    ap.add_argument(
        "--price-max",
        type=int,
        default=None,
        help="Maximum price for structure detection (e.g., 6200)",
    )

    return ap.parse_args()


def main() -> None:
    args = parse_args()
    ticker = args.ticker.upper()

    if ticker not in INSTRUMENTS:
        raise SystemExit(f"Unsupported ticker: {ticker}. Supported: {list(INSTRUMENTS)}")

    synthetic = INSTRUMENTS[ticker]["synthetic"]
    multiplier = INSTRUMENTS[ticker]["multiplier"]

    path = args.file
    if not os.path.isfile(path):
        raise SystemExit(f"Input file not found: {path}")

    log("config", "🔧", f"ticker={ticker}, synthetic={synthetic}, multiplier={multiplier}")
    log("config", "🔧", f"file={path}, publish={args.publish}")

    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    bars: List[Dict[str, Any]] = payload.get("bars") or []
    log("input", "ℹ️", f"Loaded {len(bars)} bars from file.")

    ohlc: List[Dict[str, Any]] = []
    bins_raw: Dict[int, float] = {}
    bins_tv: Dict[int, float] = {}

    for b in bars:
        t = b.get("t")
        o = b.get("o")
        h = b.get("h")
        l = b.get("l")
        c = b.get("c")
        v = b.get("v")

        ohlc.append({"t": t, "o": o, "h": h, "l": l, "c": c, "v": v})
        accumulate_raw(bins_raw, c, v, multiplier)
        accumulate_tv(bins_tv, l, h, v, multiplier)

    if bins_raw:
        price_min = min(bins_raw.keys())
        price_max = max(bins_raw.keys())
    else:
        price_min = price_max = 0

    log("build", "📊", f"Built profile: {len(bins_raw)} raw levels, {len(bins_tv)} TV levels")
    log("build", "📊", f"Price range: ${price_min:,} - ${price_max:,}")

    # Visualization for structural analysis (shows both RAW and TV)
    chart_path = args.save_chart
    if args.visualize or args.save_chart:
        visualize_profile(bins_raw, bins_tv, synthetic, save_path=chart_path)

    # AI Analysis - uses focused chart when price range specified
    ai_structures = None
    if args.ai_analyze:
        if not HAS_AI_ANALYSIS:
            log("ai", "⚠️", "AI analysis module not available")
        else:
            import tempfile

            # Generate focused chart for AI analysis
            if args.price_min or args.price_max:
                # Use focused chart for the specified price range
                ai_chart_path = tempfile.mktemp(suffix="_ai_focused.png")
                generate_ai_chart(
                    bins_tv, synthetic, ai_chart_path,
                    price_min=args.price_min, price_max=args.price_max
                )
            else:
                # Use full chart
                ai_chart_path = chart_path or tempfile.mktemp(suffix=".png")
                if not chart_path:
                    visualize_profile(bins_raw, bins_tv, synthetic, save_path=ai_chart_path)

            ai_result = analyze_chart_with_claude(ai_chart_path, model=args.ai_model)
            if ai_result:
                print_ai_analysis(ai_result)
                ai_structures = {
                    "volume_nodes": ai_result.get("volume_nodes", []),
                    "volume_wells": ai_result.get("volume_wells", []),
                    "crevasses": ai_result.get("crevasses", []),
                }

                # Generate chart with AI structures overlaid
                if chart_path:
                    base, ext = chart_path.rsplit('.', 1) if '.' in chart_path else (chart_path, 'png')
                    overlay_chart_path = f"{base}_ai_structures.{ext}"
                    print("\nGenerating chart with AI structure overlays...")
                    visualize_profile(bins_raw, bins_tv, synthetic, save_path=overlay_chart_path, structures=ai_structures)

    # Interactive structure editor
    structures = None
    if args.interactive:
        # Show AI suggestions if available
        if ai_structures:
            print("\n" + "=" * 60)
            print("AI SUGGESTIONS (you can use these as starting points)")
            print("=" * 60)
            if ai_structures.get("volume_nodes"):
                print(f"  Volume Nodes: {','.join(str(p) for p in ai_structures['volume_nodes'])}")
            if ai_structures.get("volume_wells"):
                print(f"  Volume Wells: {','.join(str(p) for p in ai_structures['volume_wells'])}")
            if ai_structures.get("crevasses"):
                crev_str = ','.join(f"{s}-{e}" for s, e in ai_structures['crevasses'])
                print(f"  Crevasses: {crev_str}")
            print("=" * 60)

        structures = interactive_structure_editor(bins_tv, synthetic)

        # Compare user structures with AI if both available
        if structures and ai_structures:
            comparison = compare_structures(ai_structures, structures)
            print_comparison(comparison)

        # Re-visualize with structures overlaid
        if structures and (structures.get("volume_nodes") or structures.get("volume_wells") or structures.get("crevasses")):
            # Generate structure overlay chart
            struct_chart_path = args.save_chart
            if struct_chart_path:
                # Add _structures suffix to filename
                base, ext = struct_chart_path.rsplit('.', 1) if '.' in struct_chart_path else (struct_chart_path, 'png')
                struct_chart_path = f"{base}_user_structures.{ext}"

            print("\nGenerating chart with user structure overlays...")
            visualize_profile(bins_raw, bins_tv, synthetic, save_path=struct_chart_path, structures=structures)

    # Auto-detect structures if none defined (neither AI nor interactive)
    if not structures and not ai_structures:
        log("struct", "🔍", "Auto-detecting structural elements from volume profile...")
        structures = auto_detect_structures(
            bins_tv,
            top_n_nodes=args.top_nodes,
            price_min=args.price_min,
            price_max=args.price_max,
        )
    elif ai_structures and not structures:
        # Use AI structures if no interactive refinement
        structures = ai_structures

    out = {
        "symbol": ticker,
        "synthetic_symbol": synthetic,
        "spy_multiplier": multiplier,
        "bin_size": BIN_SIZE,
        "min_price": price_min,
        "max_price": price_max,
        "last_updated": datetime.now(UTC).isoformat(),
        "ohlc": ohlc,
        "buckets_raw": bins_raw,
        "buckets_tv": bins_tv,
    }

    # Add structures (always - either auto-detected, AI, or user-defined)
    if structures:
        out["structures"] = structures
        log("struct", "🏗️", f"Structures: {len(structures['volume_nodes'])} nodes, "
            f"{len(structures['volume_wells'])} wells, {len(structures['crevasses'])} crevasses")

    save_to_system_redis(out)

    mode = args.publish
    if mode in ("raw", "both"):
        publish_to_market({"symbol": synthetic, "mode": "raw", "buckets": out["buckets_raw"]})
    if mode in ("tv", "both"):
        publish_to_market({"symbol": synthetic, "mode": "tv", "buckets": out["buckets_tv"]})

    log("done", "✅", f"Volume profile built for {synthetic}")


if __name__ == "__main__":
    main()
