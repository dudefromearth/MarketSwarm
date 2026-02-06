#!/usr/bin/env python3
"""
MarketSwarm — Startup Chain Loader (Global Fallback Version)

Loads chains for: I:SPX, I:NDX, SPY, QQQ
• Attempts today's chain first
• If ANY symbol fails → prompt ONCE to load next available expirations instead
• Graceful errors, clean output, no guessing
"""
import json
import redis
import os
import time
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from massive import RESTClient

# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------

API_KEY = os.getenv("MASSIVE_API_KEY", "pdjraOWSpDbg3ER_RslZYe3dmn4Y7WCC")
SYMBOLS = ["I:SPX", "I:NDX", "SPY", "QQQ"]

STRIKE_WINDOW = 30     # +/- strikes from spot
MAX_DTE = 10           # look up to 10 expirations if needed

client = RESTClient(API_KEY)


# ---------------------------------------------------------
# UTILITIES
# ---------------------------------------------------------

def ts():
    return datetime.datetime.utcnow().isoformat()


def get_spot(symbol):
    """Returns current spot or None."""
    try:
        if symbol.startswith("I:"):  # index
            snap = client.get_snapshot_indices([symbol])
            if not snap or not hasattr(snap, "results"):
                return None
            if len(snap.results) == 0:
                return None
            return snap.results[0].value
        else:  # equity ETF
            snap = client.get_snapshot_ticker("stocks", symbol)
            return snap.ticker.lastTrade.p if snap else None
    except Exception:
        return None


def get_expirations(symbol, limit=200):
    """
    Returns sorted list of expiration dates by scanning a small chain window.
    Reliable and fast.
    """
    out = set()
    try:
        for opt in client.list_snapshot_options_chain(
            symbol,
            params={"limit": limit, "order": "asc", "sort": "ticker"}
        ):
            exp = opt.details.expiration_date
            if exp:
                out.add(exp)
    except Exception:
        return []

    return sorted(out)


def load_chain_for_exp(symbol, expiration, strike_center, strike_window):
    """
    Pulls a chain for ONE expiration + strike window.
    Returns dict result describing status.
    """
    try:
        lower = strike_center - strike_window
        upper = strike_center + strike_window

        params = {
            "expiration_date.gte": expiration,
            "expiration_date.lte": expiration,
            "strike_price.gte": lower,
            "strike_price.lte": upper,
            "limit": 250,
            "order": "asc",
            "sort": "ticker"
        }

        contracts = []
        for opt in client.list_snapshot_options_chain(symbol, params=params):
            contracts.append(opt)

        return {
            "symbol": symbol,
            "expiration": expiration,
            "count": len(contracts),
            "status": "ok",
            "contracts": contracts
        }

    except Exception as e:
        return {
            "symbol": symbol,
            "expiration": expiration,
            "status": "error",
            "error": str(e)
        }


# ---------------------------------------------------------
# PER-SYMBOL LOAD ATTEMPT
# ---------------------------------------------------------

def try_load_today(symbol):
    """Attempt today's expiration chain."""
    print(f"[LOAD] Trying today for {symbol}")

    spot = get_spot(symbol)
    if spot is None:
        print(f"[WARN] Spot unavailable for {symbol}")
        return {"symbol": symbol, "status": "spot_unavailable"}

    exps = get_expirations(symbol)
    today = datetime.date.today().strftime("%Y-%m-%d")

    if today not in exps:
        print(f"[WARN] No today expiration for {symbol}")
        return {"symbol": symbol, "status": "today_exp_unavailable"}

    result = load_chain_for_exp(symbol, today, spot, STRIKE_WINDOW)

    if result["status"] != "ok" or result["count"] == 0:
        print(f"[WARN] No contracts for {symbol} today")
        return {"symbol": symbol, "status": "today_chain_empty"}

    store_chain(symbol, today, result["contracts"])
    return result


def load_next_expiration(symbol):
    """Load next available expiration."""
    print(f"[FALLBACK] Loading next expiration for {symbol}...")

    spot = get_spot(symbol)
    if spot is None:
        return {"symbol": symbol, "status": "spot_unavailable"}

    exps = get_expirations(symbol)
    today = datetime.date.today().strftime("%Y-%m-%d")

    future = [e for e in exps if e > today]
    if not future:
        return {"symbol": symbol, "status": "no_future_expirations"}

    nex = future[0]
    result = load_chain_for_exp(symbol, nex, spot, STRIKE_WINDOW)
    result["selected_expiration"] = nex
    store_chain(symbol, today, result["contracts"])
    return result

r_market = redis.Redis(host="127.0.0.1", port=6380, decode_responses=True)

def store_chain(symbol, expiration, contracts):
    """
    Store contracts into redis and verify.
    Returns dict: { status, key, stored_count }
    """
    redis_key = f"chain:{symbol}:{expiration}"

    # wipe old data
    r_market.delete(redis_key)

    # store each contract
    for opt in contracts:
        ticker = opt.details.ticker
        r_market.hset(redis_key, ticker, json.dumps(opt.to_dict()))

    # verify
    stored_count = r_market.hlen(redis_key)

    if stored_count != len(contracts):
        print(f"[STORE-ERROR] {symbol} exp={expiration} mismatch — stored {stored_count}, expected {len(contracts)}")
        return {"status": "error", "key": redis_key, "stored": stored_count}

    print(f"[STORE] {symbol} | {expiration} | {stored_count} contracts → {redis_key}")
    return {"status": "ok", "key": redis_key, "stored": stored_count}

# ---------------------------------------------------------
# MAIN ORCHESTRATION
# ---------------------------------------------------------

def main():
    while True:
        os.system("clear")
        print("=== MarketSwarm Chain Loader ===")
        print("1) Load all symbols")
        print("2) Load single symbol")
        print("3) Exit")

        choice = input("Select: ").strip()

        if choice == "3":
            return

        if choice == "2":
            sym = input("Symbol (I:SPX, I:NDX, SPY, QQQ): ").strip()
            todo = [sym]
        else:
            todo = SYMBOLS

        print(f"\n[START] Loading: {todo}\n")

        # 1. Try today's expirations for all selected symbols
        results_today = {}
        failures = []

        with ThreadPoolExecutor(max_workers=len(todo)) as pool:
            futs = {pool.submit(try_load_today, s): s for s in todo}

            for fut in as_completed(futs):
                sym = futs[fut]
                res = fut.result()
                results_today[sym] = res
                if res["status"] != "ok":
                    failures.append(sym)
                print(f"[RESULT] {sym}: {res['status']}")

        # 2. If all succeeded → done
        if not failures:
            print("\nAll symbols loaded successfully.")
            input("Press Enter to continue.")
            continue

        # 3. Prompt global fallback
        print("\nSome chains unavailable for:", failures)
        ans = input("Load next available expiration for ALL symbols? (y/n): ").strip().lower()

        if ans != "y":
            print("\nAborting fallback. Loader finished.")
            input("Press Enter to continue.")
            continue

        # 4. Load fallback expirations for ALL symbols (not just failures)
        print("\n[FALLBACK] Loading next expirations for all symbols...\n")

        fallback_results = {}
        with ThreadPoolExecutor(max_workers=len(todo)) as pool:
            futs = {pool.submit(load_next_expiration, s): s for s in todo}

            for fut in as_completed(futs):
                sym = futs[fut]
                res = fut.result()
                fallback_results[sym] = res
                print(f"[FALLBACK RESULT] {sym}: {res['status']} (exp={res.get('selected_expiration')})")

        print("\nLoader finished.")
        input("Press Enter to continue.")


if __name__ == "__main__":
    main()