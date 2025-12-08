#!/usr/bin/env python3
"""
plot_volume_profile.py
Plot the SPX volume profile over any given strike window.
"""

import argparse
import redis
import matplotlib.pyplot as plt

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min", type=int, required=True)
    ap.add_argument("--max", type=int, required=True)
    args = ap.parse_args()

    r = redis.Redis(host="localhost", port=6380, db=0, decode_responses=True)
    bins = r.hgetall("volume_profile:SPX:bins")

    xs = []
    vs = []

    for k, v in bins.items():
        k = int(k)
        if args.min <= k <= args.max:
            xs.append(k)
            vs.append(float(v))

    if not xs:
        print("No bins in range.")
        return

    plt.figure(figsize=(10,4))
    plt.bar(xs, vs, width=0.8, color="#4C72B0")
    plt.title(f"SPX Volume Profile {args.min}-{args.max}")
    plt.xlabel("SPX Price Level (0.1 increments)")
    plt.ylabel("Volume")
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    main()