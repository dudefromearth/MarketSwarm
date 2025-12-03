#!/usr/bin/env python3
"""
Massive Snapshot Options Chain Loader
=====================================

Loads options chains for one or more symbols, storing:

Per-expiration chains:
    Key:   chain:<symbol>:<expiration>
    Field: "<exp>:<strike>:<C|P>"
    Value: JSON-serialized Massive contract

Per-run time-keyed snapshot (for strategy manifold / timeline):
    Key:   massive:snapshot:<symbol>:<YYYY-MM-DDTHH:MM:SS>
    Fields:
        symbol        → "I:SPX"
        snapshot_ts   → "2025-12-02T23:16:09"
        epoch         → 1733187369 (epoch seconds)
        expirations   → JSON array of {expiration, redis_key, count}

Also:
    - massive:snapshot:<symbol>:latest → snapshot key (SET)
    - massive:snapshot:index:<symbol>  → sorted set of snapshot keys by epoch
    - massive:chain-feed (Redis Stream) gets an event per snapshot
"""

import argparse
import json
import os
from datetime import datetime, UTC, timedelta, date

import pytz
import redis
from massive import RESTClient

# ------------------------------------------------------------
# DEFAULT CONFIG (overridable via CLI)
# ------------------------------------------------------------

DEFAULT_API_KEY = os.getenv("MASSIVE_API_KEY", "pdjraOWSpDbg3ER_RslZYe3dmn4Y7WCC")

DEFAULT_SYMBOLS = ["I:SPX", "I:NDX", "I:VIX", "SPY", "QQQ"]

DEFAULT_REDIS_PREFIX = "chain"
DEFAULT_STRIKE_RANGE = 150            # ± around ATM
DEFAULT_USE_STRICT_GT_LT = False      # If True → gt/lt ; If False → gte/lte
DEFAULT_MAX_CHAIN_LIMIT = 250         # Massive's max limit for this endpoint
DEFAULT_NUM_EXPIRATIONS = 5           # 0–N DTE

US_EASTERN = pytz.timezone("US/Eastern")

# Globals initialised in main()
client: RESTClient | None = None
r: redis.Redis | None = None

# ------------------------------------------------------------
# UTILITIES
# ------------------------------------------------------------

def log(stage: str, emoji: str, msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}][loader|{stage}]{emoji} {msg}")


def round_to_nearest_5(x: float) -> int:
    return int(round(x / 5.0)) * 5


def next_trading_day(d: date) -> date:
    """Return next weekday (holidays can be added later)."""
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def determine_base_expiration() -> date:
    """
    Determine starting expiration:
    - Before 4PM ET: today's trading day
    - After 4PM ET: next trading day
    """
    now_et = datetime.now(US_EASTERN)
    today = now_et.date()

    if now_et.hour < 16:
        return next_trading_day(today)

    return next_trading_day(today + timedelta(days=1))


# ------------------------------------------------------------
# SPOT FETCHING
# ------------------------------------------------------------

def get_spot(symbol: str, debug_rest: bool = False) -> float | None:
    """Massive-compliant spot fetch for indices + ETFs."""
    assert client is not None

    try:
        if symbol.startswith("I:"):
            snap = client.get_snapshot_indices([symbol])
            results = getattr(snap, "results", snap)
            if not results:
                log(symbol, "❌", "No index snapshot results")
                return None
            spot = results[0].value
            log(symbol, "ℹ️", f"Spot: {spot}")
            return spot

        snap = client.get_snapshot_ticker("stocks", symbol)
        if debug_rest:
            log(symbol, "🧪", f"Equity snapshot raw: {snap}")

        if snap and hasattr(snap, "last_trade") and hasattr(snap.last_trade, "price"):
            spot = snap.last_trade.price
            log(symbol, "ℹ️", f"Spot: {spot}")
            return spot

        log(symbol, "❌", f"Equity snapshot missing last_trade.price: {snap}")
        return None

    except Exception as e:
        log(symbol, "💥", f"Spot fetch failed: {e}")
        import traceback; traceback.print_exc()
        return None


# ------------------------------------------------------------
# EXPIRATION HANDLING
# ------------------------------------------------------------

def get_all_expirations(symbol: str, max_chain_limit: int, debug_rest: bool = False) -> list[str]:
    """
    Collect all expirations Massive exposes via snapshot chain feed.
    Uses limit=max_chain_limit only.
    """
    assert client is not None

    try:
        out = set()
        for opt in client.list_snapshot_options_chain(
            symbol, params={"limit": max_chain_limit}
        ):
            exp = opt.details.expiration_date
            if exp:
                out.add(exp)

        exps = sorted(out)
        log(symbol, "ℹ️", f"{len(exps)} expirations available")
        if debug_rest:
            log(symbol, "🧪", f"All expirations: {exps}")
        return exps

    except Exception as e:
        log(symbol, "💥", f"Expiration fetch failed: {e}")
        import traceback; traceback.print_exc()
        return []


def filter_expirations(exps: list[str], base_exp: date, num_expirations: int) -> list[str]:
    """
    Select next num_expirations expirations starting from base_exp (inclusive).
    """
    base_str = base_exp.strftime("%Y-%m-%d")
    filtered = [e for e in exps if e >= base_str]
    return filtered[:num_expirations]


# ------------------------------------------------------------
# STRIKE FILTER PARAM BUILDER
# ------------------------------------------------------------

def strike_filters(lower: float, upper: float, strict: bool = False) -> dict:
    if strict:
        return {"strike_price.gt": lower, "strike_price.lt": upper}
    else:
        return {"strike_price.gte": lower, "strike_price.lte": upper}


# ------------------------------------------------------------
# CHAIN FETCHER
# ------------------------------------------------------------

def fetch_chain_slice(
    symbol: str,
    expiration: str,
    spot: float,
    strike_range: int,
    max_chain_limit: int,
    use_strict_gt_lt: bool,
    debug_rest: bool = False,
) -> list | None:
    """
    Fetch options for:
    - ±strike_range around ATM
    - exact expiration_date
    - Massive-compliant params
    """
    assert client is not None

    atm = round_to_nearest_5(spot)
    lower = atm - strike_range
    upper = atm + strike_range

    params = {
        "expiration_date": expiration,
        "order": "asc",
        "sort": "strike_price",
        "limit": max_chain_limit,
    }

    params.update(strike_filters(lower, upper, strict=use_strict_gt_lt))

    log(
        symbol,
        "🔎",
        f"Fetching exp={expiration}, ATM={atm}, "
        f"range=({lower}–{upper}), strict={use_strict_gt_lt}",
    )

    if debug_rest:
        log(symbol, "🧪", f"Request params: {params}")

    contracts = []
    try:
        for opt in client.list_snapshot_options_chain(symbol, params=params):
            contracts.append(opt)
    except Exception as e:
        log(symbol, "💥", f"Chain fetch failed for {expiration}: {e}")
        import traceback; traceback.print_exc()
        return None

    log(symbol, "ℹ️", f"{expiration} → {len(contracts)} contracts")
    return contracts


# ------------------------------------------------------------
# REDIS STORAGE: PER-EXP CHAIN
# ------------------------------------------------------------

def store_chain(
    symbol: str,
    expiration: str,
    contracts: list,
    redis_prefix: str,
) -> tuple[str, int]:
    """
    Write to Redis using your specified format:
        Key:   <redis_prefix>:<symbol>:<expiration>
        Field: "<exp>:<strike>:<C|P>"
        Value: raw JSON blob from Massive
    """
    assert r is not None

    redis_key = f"{redis_prefix}:{symbol}:{expiration}"
    r.delete(redis_key)

    count = 0

    for opt in contracts:
        # Convert Massive object to JSON-serializable dict
        raw = json.loads(json.dumps(opt, default=lambda o: o.__dict__))

        exp = raw["details"]["expiration_date"]
        strike = raw["details"]["strike_price"]
        cp = raw["details"]["contract_type"].upper()

        field = f"{exp}:{strike}:{cp}"

        # Store entire JSON contract
        r.hset(redis_key, field, json.dumps(raw))
        count += 1

    log(symbol, "💾", f"{expiration} → {count} → {redis_key}")
    return redis_key, count


# ------------------------------------------------------------
# REDIS STORAGE: TIME-KEYED SNAPSHOT
# ------------------------------------------------------------

def store_snapshot(symbol: str, per_exp_results: list[dict]) -> str | None:
    """
    Store a time-keyed snapshot for this loader run:

        Key: massive:snapshot:<symbol>:<YYYY-MM-DDTHH:MM:SS>
        Fields:
          symbol       → <symbol>
          snapshot_ts  → <iso-8601 second>
          epoch        → <epoch seconds>
          expirations  → JSON array of {expiration, redis_key, count}

    Also:
        massive:snapshot:<symbol>:latest → snapshot_key (SET)
        massive:snapshot:index:<symbol>  → sorted set (ZADD)
        massive:chain-feed               → XADD event
    """
    assert r is not None

    if not per_exp_results:
        log(symbol, "⚠️", "No expirations stored, skipping snapshot")
        return None

    now_utc = datetime.now(UTC)

    # ⬇️ this is the ONLY line that has to change for ms precision
    snapshot_ts = now_utc.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]  # e.g. 2025-12-03T00:35:17.123

    # keep this exactly as it was
    epoch_sec = int(now_utc.timestamp())

    snapshot_key = f"massive:snapshot:{symbol}:{snapshot_ts}"

    payload = {
        "symbol": symbol,
        "snapshot_ts": snapshot_ts,
        "epoch": epoch_sec,
        "expirations": json.dumps(per_exp_results),
    }

    r.hset(snapshot_key, mapping=payload)
    # Keep, say, 10 minutes of snapshots by default
    r.expire(snapshot_key, 60 * 10)

    # Pointer to latest snapshot
    latest_key = f"massive:snapshot:{symbol}:latest"
    r.set(latest_key, snapshot_key)

    # Sorted index for time-range queries
    index_key = f"massive:snapshot:index:{symbol}"
    r.zadd(index_key, {snapshot_key: epoch_sec})
    # Optional trim: keep last 600 entries
    r.zremrangebyrank(index_key, 0, -601)

    # Publish to chain-feed stream for downstream modelers
    try:
        r.xadd(
            "massive:chain-feed",
            {
                "symbol": symbol,
                "snapshot_key": snapshot_key,
                "snapshot_ts": snapshot_ts,
            },
        )
    except Exception as e:
        log(symbol, "⚠️", f"Failed to XADD to massive:chain-feed: {e}")

    log(symbol, "📡", f"Snapshot stored → {snapshot_key}")
    return snapshot_key


# ------------------------------------------------------------
# MAIN WORKFLOW
# ------------------------------------------------------------

def load_symbol(
    symbol: str,
    strike_range: int,
    redis_prefix: str,
    max_chain_limit: int,
    num_expirations: int,
    use_strict_gt_lt: bool,
    debug_rest: bool = False,
) -> list[dict] | None:
    log(symbol, "🚚", "LOAD")

    # 1. Spot
    spot = get_spot(symbol, debug_rest=debug_rest)
    if spot is None:
        log(symbol, "❌", "Cannot load chain: no spot")
        return None

    # 2. All expirations
    all_exps = get_all_expirations(symbol, max_chain_limit, debug_rest=debug_rest)
    if not all_exps:
        log(symbol, "❌", "No expirations found")
        return None

    # 3. Base expiration (today or next)
    base_exp = determine_base_expiration()

    # 4. Filter to next N expirations
    target_exps = filter_expirations(all_exps, base_exp, num_expirations)
    if not target_exps:
        log(
            symbol,
            "❌",
            f"No expirations after base_exp={base_exp} for num_expirations={num_expirations}",
        )
        return None

    results: list[dict] = []

    for exp in target_exps:
        log(symbol, "ℹ️", f"Loading expiration {exp}")
        contracts = fetch_chain_slice(
            symbol,
            exp,
            spot,
            strike_range=strike_range,
            max_chain_limit=max_chain_limit,
            use_strict_gt_lt=use_strict_gt_lt,
            debug_rest=debug_rest,
        )
        if not contracts:
            log(symbol, "⚠️", f"No contracts for {exp}")
            continue

        key, count = store_chain(symbol, exp, contracts, redis_prefix=redis_prefix)
        results.append({"expiration": exp, "redis_key": key, "count": count})

    # Per-run snapshot (time-keyed)
    store_snapshot(symbol, results)

    return results


def load_all_symbols(
    symbols: list[str],
    strike_range: int,
    redis_prefix: str,
    max_chain_limit: int,
    num_expirations: int,
    use_strict_gt_lt: bool,
    debug_rest: bool = False,
) -> dict:
    out: dict = {}
    for sym in symbols:
        out[sym] = load_symbol(
            sym,
            strike_range=strike_range,
            redis_prefix=redis_prefix,
            max_chain_limit=max_chain_limit,
            num_expirations=num_expirations,
            use_strict_gt_lt=use_strict_gt_lt,
            debug_rest=debug_rest,
        )
    return out


# ------------------------------------------------------------
# EXECUTION ENTRY
# ------------------------------------------------------------

def main() -> None:
    global client, r

    parser = argparse.ArgumentParser()

    parser.add_argument("--symbols", type=str, required=False,
                        help="Space-separated list of symbols")
    parser.add_argument("--strike-range", type=int, required=False)
    parser.add_argument("--redis-prefix", type=str, required=False)
    parser.add_argument("--api-key", type=str, required=False)
    parser.add_argument("--strict", type=str, required=False,
                        help="true/false for strict gt/lt vs gte/lte")
    parser.add_argument("--expirations", type=int, required=False)
    parser.add_argument("--redis-url", type=str, required=False)
    parser.add_argument("--debug-rest", action="store_true",
                        help="Enable verbose REST logging")

    args = parser.parse_args()

    # Resolve configuration with overrides
    symbols = DEFAULT_SYMBOLS
    if args.symbols:
        symbols = args.symbols.split()

    strike_range = args.strike_range if args.strike_range is not None else DEFAULT_STRIKE_RANGE
    redis_prefix = args.redis_prefix if args.redis_prefix is not None else DEFAULT_REDIS_PREFIX

    api_key = args.api_key or DEFAULT_API_KEY

    use_strict = DEFAULT_USE_STRICT_GT_LT
    if args.strict:
        use_strict = args.strict.lower() == "true"

    num_expirations = args.expirations if args.expirations is not None else DEFAULT_NUM_EXPIRATIONS

    redis_url = args.redis_url or "redis://127.0.0.1:6380"

    debug_rest = bool(args.debug_rest)

    # Wire Redis + Massive client
    r = redis.Redis.from_url(redis_url, decode_responses=True)
    client = RESTClient(api_key)

    log("config", "🔧", f"Symbols:           {symbols}")
    log("config", "🔧", f"Strike range:      ±{strike_range}")
    log("config", "🔧", f"Redis prefix:      {redis_prefix}")
    log("config", "🔧", f"Num expirations:   {num_expirations}")
    log("config", "🔧", f"Strict gt/lt:      {use_strict}")
    log("config", "🔧", f"Redis URL:         {redis_url}")
    log("config", "🔧", f"Debug REST:        {debug_rest}")

    load_all_symbols(
        symbols=symbols,
        strike_range=strike_range,
        redis_prefix=redis_prefix,
        max_chain_limit=DEFAULT_MAX_CHAIN_LIMIT,
        num_expirations=num_expirations,
        use_strict_gt_lt=use_strict,
        debug_rest=debug_rest,
    )


if __name__ == "__main__":
    main()