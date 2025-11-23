#!/usr/bin/env python3
"""
Volume Profile Chart Generator
Renders a vertical SPX volume profile from stored (SPY→SPX-derived) bins,
with professional orientation (right-to-left) matching trading platforms.
"""

import json
import argparse
import numpy as np
import matplotlib.pyplot as plt
from typing import Dict, Any


# -----------------------------------------------------------------------------
# Argument Parsing
# -----------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description="SPX Volume Profile Chart Generator")

    p.add_argument("--input", required=True, help="Path to volume_profile.json")
    p.add_argument("--output", default="chart.jpg", help="Output JPEG filename")

    p.add_argument("--width", type=int, default=900)
    p.add_argument("--height", type=int, default=1400)

    # Structural markers OFF by default (matches screenshot)
    p.add_argument("--struct-threshold", type=float, default=2.0)
    p.add_argument("--no-struct", action="store_true", default=True)

    # Price-range
    p.add_argument("--range", nargs=2, type=int, metavar=("LOW", "HIGH"))
    p.add_argument("--range-auto", action="store_true", default=True)

    # Orientation — DEFAULT = professional (bars left, price on right)
    p.add_argument(
        "--orientation",
        choices=["left", "right"],
        default="right",
        help="right (default): price on right, bars extend left"
    )

    return p.parse_args()


# -----------------------------------------------------------------------------
# Price-range selector
# -----------------------------------------------------------------------------

def compute_price_range(prices, args):
    prices = np.array(prices)
    ath = prices.max()

    if args.range:
        return args.range[0], args.range[1]

    return ath - 250, ath


# -----------------------------------------------------------------------------
# Rendering
# -----------------------------------------------------------------------------

def render_volume_profile(
    data: Dict[str, Any],
    output_path: str,
    width: int,
    height: int,
    structural_markers: bool,
    struct_threshold: float,
    price_low: int,
    price_high: int,
    orientation: str
):
    """Render a JPEG vertical volume profile from SPX bucket data."""

    buckets = data["buckets"]

    # Convert keys → ints
    all_prices = np.array(sorted(int(p) for p in buckets.keys()))
    all_vols   = np.array([float(buckets[str(p)]) for p in all_prices])

    # Price slice
    mask = (all_prices >= price_low) & (all_prices <= price_high)
    prices = all_prices[mask]
    volumes = all_vols[mask]

    if len(prices) == 0:
        raise ValueError("No volume-profile data in selected range.")

    # Normalize
    max_vol = volumes.max() if volumes.max() > 0 else 1
    norm_vol = volumes / max_vol

    # -------------------------------------------------------------------------
    # Plot
    # -------------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(width / 100, height / 100), dpi=100)

    fig.patch.set_facecolor("#111216")
    ax.set_facecolor("#111216")

    # -------------------------------------------------------------------------
    # TRUE MIRRORED ORIENTATION (default)
    # -------------------------------------------------------------------------
    if orientation == "right":
        # Bars extend left — TRUE mirror
        ax.barh(
            prices,
            norm_vol,       # POSITIVE WIDTH
            height=1.0,
            color="#4B84F2",
            edgecolor="#4B84F2",
            linewidth=0.25,
            align="edge"
        )

        # Force bars to extend left by reversing axis
        ax.set_xlim(1.0, 0.0)

        # Price axis on RIGHT
        ax.yaxis.tick_right()
        ax.yaxis.set_label_position("right")

    else:
        # Normal orientation — bars extend right
        ax.barh(
            prices,
            norm_vol,
            height=1.0,
            color="#4B84F2",
            edgecolor="#4B84F2",
            linewidth=0.25,
            align="edge"
        )
        ax.set_xlim(0.0, 1.0)
        ax.yaxis.tick_left()
        ax.yaxis.set_label_position("left")

    # -------------------------------------------------------------------------
    # Structural Markers (disabled by default)
    # -------------------------------------------------------------------------
    if structural_markers:
        dv = np.diff(volumes)
        sign = np.sign(dv)
        zero_crossings = np.where(np.diff(sign))[0]

        hvn = []
        lvn = []

        for idx in zero_crossings:
            if idx + 2 >= len(volumes):
                continue

            left = volumes[idx]
            mid  = volumes[idx + 1]
            right = volumes[idx + 2]

            if mid > left and mid > right and mid > struct_threshold:
                hvn.append(prices[idx + 1])
            if mid < left and mid < right:
                lvn.append(prices[idx + 1])

        # Plot markers on right margin (constant x=1.03)
        for p in hvn:
            ax.plot(1.03, p, "s", markersize=5, color="#FFD84A",
                    transform=ax.get_yaxis_transform())

        for p in lvn:
            ax.plot(1.03, p, "s", markersize=5, color="#00FFAA",
                    transform=ax.get_yaxis_transform())

    # -------------------------------------------------------------------------
    # Aesthetics
    # -------------------------------------------------------------------------
    ax.tick_params(colors="#CCCCCC", labelsize=11)
    ax.set_xlabel("", color="#CCCCCC")
    ax.set_ylabel("Price (SPX)", color="#CCCCCC")

    # Removes excess padding so bars reach edge
    ax.margins(x=0)

    plt.tight_layout()
    plt.savefig(output_path, format="jpeg", dpi=100, facecolor=fig.get_facecolor())
    plt.close(fig)


# -----------------------------------------------------------------------------
# Entry
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    args = parse_args()

    with open(args.input, "r") as f:
        payload = json.load(f)

    all_prices = [int(p) for p in payload["buckets"].keys()]
    lo, hi = compute_price_range(all_prices, args)

    print(f"📈 Rendering volume profile {lo} → {hi}")
    print(f"🧭 Orientation: {args.orientation}")

    render_volume_profile(
        payload,
        output_path=args.output,
        width=args.width,
        height=args.height,
        structural_markers=not args.no_struct,
        struct_threshold=args.struct_threshold,
        price_low=lo,
        price_high=hi,
        orientation=args.orientation,
    )

    print(f"✅ Chart saved → {args.output}")