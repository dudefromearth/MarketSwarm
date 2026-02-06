#!/usr/bin/env python3
"""
Massive Snapshot Options Chain Loader — Analytics-Optimized Edition
====================================================================

Loads options chains, storing in query-ready Redis structures:
  gex:<symbol>:<exp> → ZSET strike → net gamma (OI * γ * 100, signed C/P)
  dex:<symbol>:<exp> → ZSET strike → net delta
  vex:<symbol>:<exp> → ZSET strike → net vega
  oi:<symbol>:<exp>  → ZSET strike → total OI
  vol:<symbol>:<exp> → ZSET strike → total volume
  iv:<symbol>:<exp>  → ZSET strike → IV
  opt:<symbol>:<exp>:<strike> → HASH C/P → compact JSON

Snapshot tracks totals; stream fires for models.
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

# IMPORTANT:
# - We no longer hide behind a baked-in key.
# - DEFAULT_API_KEY will be empty unless MASSIVE_API_KEY is set in env.
DEFAULT_API_KEY = os.getenv("MASSIVE_API_KEY", "")

DEFAULT_SYMBOLS = ["I:SPX", "I:NDX", "I:VIX", "SPY", "QQQ"]

DEFAULT_STRIKE_RANGE = 150            # ± around ATM
DEFAULT_USE_STRICT_GT_LT = False      # If True → gt/lt ; If False → gte/lte
DEFAULT_MAX_CHAIN_LIMIT = 250         # Massive's max limit for this endpoint
DEFAULT_NUM_EXPIRATIONS = 5           # 0–N DTE

US_EASTERN = pytz.timezone("US/Eastern")

# Globals initialised in main()
client: RESTClient | None = None
r: redis.Redis | None = None
KEEP_RAW_BLOBS = False  # Set via --keep-raw flag

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
            if debug_rest:
                log(symbol, "🌐", "Calling client.get_snapshot_indices(...)")
            snap = client.get_snapshot_indices([symbol])
            results = getattr(snap, "results", snap)
            if not results:
                log(symbol, "❌", "No index snapshot results")
                return None
            spot = results[0].value
            log(symbol, "ℹ️", f"Spot: {spot}")
            return spot

        if debug_rest:
            log(symbol, "🌐", 'Calling client.get_snapshot_ticker("stocks", symbol)')
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
        if debug_rest:
            log(symbol, "🌐", "Calling client.list_snapshot_options_chain(...) for expirations")

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
        if debug_rest:
            log(symbol, "🌐", "Calling client.list_snapshot_options_chain(...) for contracts")
        for opt in client.list_snapshot_options_chain(symbol, params=params):
            contracts.append(opt)
    except Exception as e:
        log(symbol, "💥", f"Chain fetch failed for {expiration}: {e}")
        import traceback; traceback.print_exc()
        return None

    log(symbol, "ℹ️", f"{expiration} → {len(contracts)} contracts")
    return contracts


# ------------------------------------------------------------
# REDIS STORAGE: ANALYTICS-OPTIMIZED (NEW)
# ------------------------------------------------------------

def store_analytics_optimized(
    symbol: str,
    expiration: str,
    contracts: list,
) -> tuple[str, int, int]:
    """
    Stores in sorted sets + compact hash (no more JSON blobs).
    Returns (redis_key for compat, total_contracts, active_contracts)
    """
    assert r is not None

    # Compat key (for snapshot; points to nothing now, but keeps API same)
    compat_key = f"chain:{symbol}:{expiration}"

    pipe = r.pipeline()
    total = 0
    active = 0

    raw_key = f"raw:{symbol}:{expiration}"  # Optional debug blobs

    for opt in contracts:
        total += 1

        # Convert to dict (handles Massive objects)
        raw = json.loads(json.dumps(opt, default=lambda o: o.__dict__))

        # Extract using YOUR JSON format (top-level fields)
        strike = raw.get("strike")
        cp_full = raw.get("type", "").lower()  # "call" or "put"
        cp = "C" if cp_full == "call" else "P" if cp_full == "put" else ""
        oi = float(raw.get("oi") or 0)
        volume = float(raw.get("volume") or 0)
        iv = float(raw.get("iv") or 0)
        delta = float(raw.get("delta") or 0)
        gamma = float(raw.get("gamma") or 0)
        vega = float(raw.get("vega") or 0)
        mid = float(raw.get("mid") or 0)

        if not cp or (oi == 0 and volume == 0):
            continue  # Skip invalids/dead
        active += 1

        sign = 1 if cp == "C" else -1

        # Primary surfaces (ZSETs)
        pipe.zincrby(f"gex:{symbol}:{expiration}", strike, sign * oi * gamma * 100)
        pipe.zincrby(f"dex:{symbol}:{expiration}", strike, sign * oi * delta * 100)
        pipe.zincrby(f"vex:{symbol}:{expiration}", strike, sign * oi * vega)
        pipe.zincrby(f"oi:{symbol}:{expiration}", strike, oi)
        pipe.zincrby(f"vol:{symbol}:{expiration}", strike, volume)
        pipe.zadd(f"iv:{symbol}:{expiration}", {strike: iv}, nx=True)

        # Compact hash per strike
        compact = {
            "oi": int(oi),
            "vol": int(volume),
            "iv": round(iv, 4),
            "delta": round(delta, 4),
            "gamma": gamma,
            "vega": round(vega, 4),
            "mid": round(mid, 2),
        }
        pipe.hset(f"opt:{symbol}:{expiration}:{strike}", cp, json.dumps(compact))

        # Optional raw blob
        if KEEP_RAW_BLOBS:
            field = f"{expiration}:{strike}:{cp}"
            pipe.hset(raw_key, field, json.dumps(raw))

    # TTLs: 2 weeks analytics, 1 day raw
    analytics_keys = [f"gex:{symbol}:{expiration}", f"dex:{symbol}:{expiration}",
                      f"vex:{symbol}:{expiration}", f"oi:{symbol}:{expiration}",
                      f"vol:{symbol}:{expiration}", f"iv:{symbol}:{expiration}"]
    for key in analytics_keys:
        pipe.expire(key, 86400 * 14)

    strike_set = set(c.get("strike") for c in [json.loads(json.dumps(opt, default=lambda o: o.__dict__)) for opt in contracts] if c.get("strike"))
    for strike in strike_set:
        pipe.expire(f"opt:{symbol}:{expiration}:{strike}", 86400 * 14)

    if KEEP_RAW_BLOBS:
        pipe.expire(raw_key, 86400)

    pipe.execute()

    log(symbol, "💾", f"{expiration} → {active}/{total} active → {compat_key} (optimized)")
    return compat_key, total, active


# ------------------------------------------------------------
# REDIS STORAGE: TIME-KEYED SNAPSHOT (MINOR UPDATE)
# ------------------------------------------------------------

def store_snapshot(symbol: str, per_exp_results: list[dict]) -> str | None:
    """
    Store a time-keyed snapshot for this loader run:

        Key: massive:snapshot:<symbol>:<YYYY-MM-DDTHH:MM:SS.mmm>
        Fields:
          symbol        → <symbol>
          snapshot_ts   → <iso-8601 millis>
          epoch         → <epoch seconds>
          expirations   → JSON array of {expiration, redis_key, total_contracts, active_oi_contracts}

    Also:
        massive:snapshot:<symbol>:latest → snapshot key (SET)
        massive:snapshot:index:<symbol>  → sorted set (ZADD)
        massive:chain-feed               → XADD event
    """
    assert r is not None

    if not per_exp_results:
        log(symbol, "⚠️", "No expirations stored, skipping snapshot")
        return None

    now_utc = datetime.now(UTC)

    # millisecond precision
    snapshot_ts = now_utc.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]

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
# MAIN WORKFLOW (UPDATED CALLS)
# ------------------------------------------------------------

def load_symbol(
    symbol: str,
    strike_range: int,
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

        key, total, active = store_analytics_optimized(symbol, exp, contracts)
        results.append({
            "expiration": exp,
            "redis_key": key,  # Compat
            "total_contracts": total,
            "active_oi_contracts": active
        })

    # Per-run snapshot (time-keyed)
    store_snapshot(symbol, results)

    return results


def load_all_symbols(
    symbols: list[str],
    strike_range: int,
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
            max_chain_limit=max_chain_limit,
            num_expirations=num_expirations,
            use_strict_gt_lt=use_strict_gt_lt,
            debug_rest=debug_rest,
        )
    return out


# ------------------------------------------------------------
# EXECUTION ENTRY (ADDED KEY RESOLUTION + HTTP-LAYER LOGGING)
# ------------------------------------------------------------

def main() -> None:
    global client, r, KEEP_RAW_BLOBS

    parser = argparse.ArgumentParser()

    parser.add_argument("--symbols", type=str, required=False,
                        help="Space-separated list of symbols")
    parser.add_argument("--strike-range", type=int, required=False)
    parser.add_argument("--api-key", type=str, required=False)
    parser.add_argument("--strict", type=str, required=False,
                        help="true/false for strict gt/lt vs gte/lte")
    parser.add_argument("--expirations", type=int, required=False)
    parser.add_argument("--redis-url", type=str, required=False)
    parser.add_argument("--debug-rest", action="store_true",
                        help="Enable verbose REST logging")
    parser.add_argument("--keep-raw", action="store_true",
                        help="Keep raw JSON blobs for 24h (debug only)")

    args = parser.parse_args()

    # --------------------------------------------------------
    # API key resolution (explicit + debuggable)
    # --------------------------------------------------------
    raw_env_key = os.getenv("MASSIVE_API_KEY")
    env_api_key = (raw_env_key or "").strip()
    cli_api_key = (args.api_key or "").strip()

    if cli_api_key:
        api_key = cli_api_key
        key_source = "--api-key"
    elif env_api_key:
        api_key = env_api_key
        key_source = "MASSIVE_API_KEY env"
    else:
        api_key = DEFAULT_API_KEY.strip()
        key_source = "DEFAULT_API_KEY constant"

    if not api_key:
        log("config", "❌", "No API key provided. Set MASSIVE_API_KEY or pass --api-key.")
        return

    # For this debugging pass, log the full key so you can 1:1 confirm.
    log("config", "🔑", f"API key source: {key_source}")
    log("config", "🔑", f"MASSIVE_API_KEY (raw env) = {raw_env_key!r}")
    log("config", "🔑", f"Final API key used = {api_key!r}")

    # --------------------------------------------------------
    # Resolve rest of configuration with overrides
    # --------------------------------------------------------
    symbols = DEFAULT_SYMBOLS
    if args.symbols:
        symbols = args.symbols.split()

    strike_range = args.strike_range if args.strike_range is not None else DEFAULT_STRIKE_RANGE

    use_strict = DEFAULT_USE_STRICT_GT_LT
    if args.strict:
        use_strict = args.strict.lower() == "true"

    num_expirations = args.expirations if args.expirations is not None else DEFAULT_NUM_EXPIRATIONS

    redis_url = args.redis_url or "redis://127.0.0.1:6380"

    debug_rest = bool(args.debug_rest)

    KEEP_RAW_BLOBS = bool(args.keep_raw)

    # Wire Redis
    r = redis.Redis.from_url(redis_url, decode_responses=True)

    # --------------------------------------------------------
    # Construct REST client + instrument HTTP layer
    # --------------------------------------------------------
    client_obj = RESTClient(api_key)
    client = client_obj  # assign to global

    log("config", "🧪", f"RESTClient type: {type(client_obj)}")
    log("config", "🧪", f"RESTClient __dict__ keys: {list(getattr(client_obj, '__dict__', {}).keys())}")
    log("config", "🧪", f"RESTClient __dict__: {getattr(client_obj, '__dict__', {})!r}")

    # Monkey-patch _get to log path + options (where headers/api key usually live)
    if hasattr(client_obj, "_get"):
        original_get = client_obj._get

        def logging_get(*a, _debug=debug_rest, **kw):
            try:
                path = kw.get("path", None)
                options = kw.get("options", None)
                if _debug:
                    log("rest", "🌐", f"_get called with path={path!r}, options={options!r}")
            except Exception as e:
                log("rest", "⚠️", f"Failed to log _get call: {e}")
            return original_get(*a, **kw)

        client_obj._get = logging_get  # type: ignore[attr-defined]
        log("config", "🧪", "Wrapped RESTClient._get with logging shim (path + options).")
    else:
        log("config", "⚠️", "RESTClient has no _get attribute; cannot log HTTP layer.")

    log("config", "🔧", f"Symbols:           {symbols}")
    log("config", "🔧", f"Strike range:      ±{strike_range}")
    log("config", "🔧", f"Num expirations:   {num_expirations}")
    log("config", "🔧", f"Strict gt/lt:      {use_strict}")
    log("config", "🔧", f"Redis URL:         {redis_url}")
    log("config", "🔧", f"Debug REST:        {debug_rest}")
    log("config", "🔧", f"Keep raw blobs:    {KEEP_RAW_BLOBS}")

    load_all_symbols(
        symbols=symbols,
        strike_range=strike_range,
        max_chain_limit=DEFAULT_MAX_CHAIN_LIMIT,
        num_expirations=num_expirations,
        use_strict_gt_lt=use_strict,
        debug_rest=debug_rest,
    )


if __name__ == "__main__":
    main()