#!/usr/bin/env python3
"""
convexity_worker.py — MASSIVE version
-------------------------------------

THIS WORKER IS FULLY SUPPRESSED.

• Reads SPX latest_full_raw from MARKET_REDIS
• Summarizes chain (spot/volume/OI/IV aggregates)
• Calls Convexity Assistant
• Prints ONLY to STDOUT
• DOES NOT WRITE ANYTHING BACK TO REDIS
• DOES NOT PUBLISH ANY EVENTS
• DOES NOT MAINTAIN ANY HISTORY
• NO THREAD IDS, NO TRAILS, NO DIGESTS

This is placeholder logic until Convexity is fully integrated with Vexy AI.
"""

import os
import json
import time
import signal
import statistics
import redis
from openai import OpenAI
from datetime import datetime, timezone

# -------------------------------------------------------------------
# ENV
# -------------------------------------------------------------------

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID = os.getenv("CONVEXITY_ASSISTANT_ID", "")

REDIS_URL = os.getenv("MARKET_REDIS_URL", "redis://127.0.0.1:6380")
SYMBOL = os.getenv("SYMBOL", "SPX")

INTERVAL_SECS = int(os.getenv("CONVEXITY_INTERVAL_SECS", "7200"))

# -------------------------------------------------------------------
# Init
# -------------------------------------------------------------------

r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
client = OpenAI(api_key=OPENAI_API_KEY)

_running = True


def _handle_stop(signum, frame):
    global _running
    _running = False
    print(f"[convexity_worker] STOP signal {signum}")


signal.signal(signal.SIGINT, _handle_stop)
signal.signal(signal.SIGTERM, _handle_stop)


# -------------------------------------------------------------------
# HELPERS
# -------------------------------------------------------------------

def get_latest_raw(symbol: str):
    """Fetch raw chain currently stored in market Redis."""
    ptr = r.get(f"{symbol}:latest_full_raw")
    if not ptr:
        raise RuntimeError("No latest_full_raw pointer for SPX.")
    raw = r.get(ptr)
    if not raw:
        raise RuntimeError(f"Pointer exists but payload missing: {ptr}")
    return json.loads(raw)


def summarize_snapshot_enhanced(raw: dict, symbol: str = None) -> dict:
    """Same summarizer Conor uses, retained so Convexity reasoning stays valid."""
    symbol = symbol or raw.get("symbol") or "SPX"
    contracts = raw.get("contracts") or []
    spot_val = raw.get("spot")

    call_count = 0
    put_count = 0

    all_ivs = []
    call_ivs = []
    put_ivs = []

    total_contract_volume = 0.0
    total_contract_oi = 0.0

    for c in contracts:
        d = c.get("details") or {}
        g = c.get("greeks") or {}

        typ = (d.get("contract_type") or "").lower()
        iv = g.get("iv") or c.get("implied_volatility")
        vol = c.get("volume") or 0
        oi = c.get("open_interest") or 0

        try:
            total_contract_volume += float(vol)
            total_contract_oi += float(oi)
        except:
            pass

        if iv is not None:
            try:
                iv = float(iv)
            except:
                iv = None

        if typ == "call":
            call_count += 1
            if iv is not None: call_ivs.append(iv)
        elif typ == "put":
            put_count += 1
            if iv is not None: put_ivs.append(iv)

        if iv is not None:
            all_ivs.append(iv)

    def avg(vals):
        return round(sum(vals) / len(vals), 4) if vals else None

    summary = {
        "symbol": symbol,
        "snapshot_ts": raw.get("ts"),
        "spot": spot_val,
        "contracts_count": len(contracts),
        "calls": call_count,
        "puts": put_count,
        "total_open_interest": total_contract_oi,
        "total_volume": total_contract_volume,
        "iv": {
            "avg": avg(all_ivs),
            "call_avg": avg(call_ivs),
            "put_avg": avg(put_ivs),
        }
    }
    return summary


# -------------------------------------------------------------------
#  CONVEXITY CALL (SUPPRESSED STORAGE)
# -------------------------------------------------------------------

def ask_convexity(snapshot_summary: dict) -> str:
    """Call Convexity assistant – no thread_keeping, no persistence."""

    header = (
        f"SPX Snapshot — Spot={snapshot_summary.get('spot')} "
        f"Volume={snapshot_summary.get('total_volume')} "
        f"OI={snapshot_summary.get('total_open_interest')}\n\n"
    )

    # The model may reference qualitative structure — allowed
    policy = (
        "You are Convexity, an options structuring analyst.\n"
        "Write ONLY qualitative insights (no numbers).\n"
        "Focus on:\n"
        "- brief snapshot takeaway (no digits),\n"
        "- 2–3 structure observations,\n"
        "- 1–2 watchlist bullets.\n"
        "150 words max.\n"
    )

    usr = (
        f"{policy}\n"
        "Snapshot JSON:\n"
        f"{json.dumps(snapshot_summary, indent=2)}\n"
    )

    # Single-shot assistant run (no thread)
    resp = client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {"role": "system", "content": "You are Convexity. Respond with qualitative analysis only."},
            {"role": "user", "content": usr}
        ],
        max_tokens=400,
    )

    out = resp.choices[0].message.content.strip()
    return header + out


# -------------------------------------------------------------------
# PUBLIC RUNNERS
# -------------------------------------------------------------------

def run_once():
    """Perform a single evaluation of the current market chain."""
    print("[convexity_worker] Running single evaluation…")

    raw = get_latest_raw(SYMBOL)
    summary = summarize_snapshot_enhanced(raw, SYMBOL)
    text = ask_convexity(summary)

    print("\n\n=== CONVEXITY OUTPUT (SUPPRESSED MODE) ===\n")
    print(text)
    print("\n=== END ===\n")
    return text


def run_loop():
    """Loop mode — still suppressed, just prints every N seconds."""
    print(f"[convexity_worker] Loop start — every {INTERVAL_SECS}s")

    while _running:
        try:
            run_once()
        except Exception as e:
            print(f"[convexity_worker] ERROR: {e}")

        # interruptible sleep
        for _ in range(INTERVAL_SECS * 10):
            if not _running:
                break
            time.sleep(0.1)

    print("[convexity_worker] Exiting loop.")


# -------------------------------------------------------------------
# CLI
# -------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--once", action="store_true")
    p.add_argument("--loop", action="store_true")
    args = p.parse_args()

    if args.once:
        run_once()
    else:
        run_loop()