#!/usr/bin/env python3
"""
Volume Profile Chart Generator — Refactored + Optional JSON Dump

Adds:
  --dump-json
Dump the EXACT dataset used for chart rendering, after:
  • mode selection (raw/tv)
  • range slicing
  • normalization of price keys

Output JSON filename = same basename as --output, but .json
Example:
  --output chart.jpg → chart.json

If --dump-json is used, NO chart is rendered.
"""

import json
import argparse
import numpy as np
import matplotlib.pyplot as plt
from typing import Dict, Any
import os


# -------------------------------------------------------------
# Argument Parsing
# -------------------------------------------------------------
def parse_args():
    p = argparse.ArgumentParser(description="SPX Volume Profile Chart Generator — Refactored")

    p.add_argument("--input", required=True, help="Path to volume_profile.json")
    p.add_argument("--output", default="chart.jpg", help="Output JPEG filename")

    p.add_argument("--width", type=int, default=900)
    p.add_argument("--height", type=int, default=1400)

    p.add_argument("--struct-threshold", type=float, default=2.0)
    p.add_argument("--struct",
                   choices=["on", "off"],
                   default="on",
                   help="Enable or disable structural analysis")

    p.add_argument("--range", nargs=2, type=int, metavar=("LOW", "HIGH"))
    p.add_argument("--range-auto", action="store_true", default=True)

    p.add_argument(
        "--orientation",
        choices=["left", "right"],
        default="right",
        help="right (default): price on right, bars extend left"
    )

    p.add_argument(
        "--mode",
        choices=["raw", "tv"],
        default="raw",
        help="Select raw or TradingView-style dataset (with fallback)"
    )

    p.add_argument(
        "--dump-json",
        action="store_true",
        help="Dump the dataset used to render (instead of creating chart)"
    )

    return p.parse_args()


# -------------------------------------------------------------
# Dataset Helpers
# -------------------------------------------------------------
def pick_dataset(payload: dict, mode: str) -> dict:
    if mode == "raw" and "buckets_raw" in payload:
        return payload["buckets_raw"]
    if mode == "tv" and "buckets_tv" in payload:
        return payload["buckets_tv"]

    # fallback cascade
    if "buckets_raw" in payload:
        print("⚠️ Requested mode not found — using RAW dataset.")
        return payload["buckets_raw"]
    if "buckets_tv" in payload:
        print("⚠️ Requested mode not found — using TV dataset.")
        return payload["buckets_tv"]
    if "buckets" in payload:
        print("⚠️ Legacy dataset detected — using 'buckets'.")
        return payload["buckets"]

    raise ValueError("No recognizable bucket dataset found in JSON.")


def compute_price_range(prices, args):
    prices = np.array(prices)
    ath = prices.max()

    if args.range:
        return args.range[0], args.range[1]

    return ath - 300, ath


def slice_range(dataset: dict, lo: int, hi: int) -> dict:
    return {
        str(p): float(vol)
        for p, vol in dataset.items()
        if lo <= int(p) <= hi
    }


# -------------------------------------------------------------
# Rendering
# -------------------------------------------------------------
def render_chart(synthetic: str, buckets: dict, args):
    prices = np.array(sorted(int(p) for p in buckets.keys()))
    volumes = np.array([float(buckets[str(p)]) for p in prices])

    if len(prices) == 0:
        raise ValueError("No volume-profile data in selected range.")

    max_vol = volumes.max() if volumes.max() > 0 else 1
    norm = volumes / max_vol

    fig, ax = plt.subplots(figsize=(args.width / 100, args.height / 100), dpi=100)
    fig.patch.set_facecolor("#111216")
    ax.set_facecolor("#111216")

    # Orientation
    if args.orientation == "right":
        ax.barh(prices, norm, height=1.0, color="#4B84F2",
                edgecolor="#4B84F2", linewidth=0.25, align="edge")
        ax.set_xlim(1.0, 0.0)
        ax.yaxis.tick_right()
        ax.yaxis.set_label_position("right")
    else:
        ax.barh(prices, norm, height=1.0, color="#4B84F2",
                edgecolor="#4B84F2", linewidth=0.25, align="edge")
        ax.set_xlim(0.0, 1.0)
        ax.yaxis.tick_left()
        ax.yaxis.set_label_position("left")

    # Structural markers
    if args.struct == "on":
        dv = np.diff(volumes)
        sign = np.sign(dv)
        zero = np.where(np.diff(sign))[0]
        hvn, lvn = [], []

        for idx in zero:
            if idx + 2 >= len(volumes):
                continue
            left, mid, right = volumes[idx], volumes[idx+1], volumes[idx+2]
            if mid > left and mid > right and mid > args.struct_threshold:
                hvn.append(prices[idx+1])
            if mid < left and mid < right:
                lvn.append(prices[idx+1])

        for p in hvn:
            ax.plot(1.03, p, "s", markersize=5, color="#FFD84A",
                    transform=ax.get_yaxis_transform())
        for p in lvn:
            ax.plot(1.03, p, "s", markersize=5, color="#00FFAA",
                    transform=ax.get_yaxis_transform())

    # Cosmetics
    ax.tick_params(colors="#CCCCCC", labelsize=11)
    ax.set_ylabel(f"Price ({synthetic})", color="#CCCCCC")
    ax.margins(x=0)

    plt.tight_layout()
    plt.savefig(args.output, format="jpeg", dpi=100, facecolor=fig.get_facecolor())
    plt.close(fig)


# -------------------------------------------------------------
# Main
# -------------------------------------------------------------
if __name__ == "__main__":
    args = parse_args()

    with open(args.input, "r") as f:
        payload = json.load(f)

    dataset = pick_dataset(payload, args.mode)
    synthetic = payload.get("synthetic_symbol", "SPX")

    all_prices = [int(p) for p in dataset.keys()]
    lo, hi = compute_price_range(all_prices, args)

    sliced = slice_range(dataset, lo, hi)

    # ---------------------------------------------------------
    # JSON DUMP OPTION
    # ---------------------------------------------------------
    if args.dump_json:
        # Ensure os is available
        import os
        import sys

        # Build JSON object
        dump_obj = {
            "synthetic_symbol": synthetic,
            "mode": args.mode,
            "price_low": int(lo),
            "price_high": int(hi),
            "buckets": {str(int(p)): float(v) for p, v in sliced.items()}
        }

        # Derive output JSON filename
        base, _ = os.path.splitext(args.output)
        out_json = base + ".json"

        # Write to disk
        with open(out_json, "w") as f:
            json.dump(dump_obj, f, indent=2)

        print(f"📤 Dumped dataset → {out_json}")

        # Exit cleanly BEFORE chart rendering
        sys.exit(0)

    # ---------------------------------------------------------
    # Chart Rendering
    # ---------------------------------------------------------
    print(f"📈 Rendering volume profile ({args.mode}) {lo} → {hi}")
    print(f"🧭 Orientation: {args.orientation}")

    render_chart(synthetic, sliced, args)

    print(f"✅ Chart saved → {args.output}")