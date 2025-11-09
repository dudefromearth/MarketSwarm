# volume_profile_worker.py  (SPY minute bars → SPX strike bins, rolling 3/6M, daemon)
import os, sys, json, time, signal, math
from datetime import datetime, timezone, timedelta, date
from typing import Dict, List, Tuple, Optional
from threading import Event
from collections import defaultdict

import requests
import redis

# =========================
# ENV / CONFIG
# =========================
POLYGON_API      = os.getenv("POLYGON_API", "https://api.polygon.io")
POLYGON_API_KEY  = os.getenv("POLYGON_API_KEY", "R5TbDLsxMtu8vQvUlax8Af9tJwGevvOl")
# Source data ticker (equities minute bars)
SPY_TICKER       = os.getenv("SPY_TICKER", "SPY")

# Display/Redis namespace stays SPX so front-end keys remain unchanged
SYMBOL           = os.getenv("SYMBOL", "SPX")

# Mapping SPY→SPX: 0.1 SPY ≈ 1.0 SPX strike
# Default 0.01 SPY → ~1 SPX point bins after ×10 scale
BIN_SIZE_SPY     = float(os.getenv("VOLUME_PROFILE_BIN_SPY", "0.01"))
SPX_SCALE        = float(os.getenv("VOLUME_PROFILE_SPX_SCALE", "10.0"))  # SPY price * 10 = SPX level
BIN_MODE         = os.getenv("VOLUME_PROFILE_MODE", "spread").lower()   # "close" or "spread"
# "spread": distributes each minute bar's volume across low..high bins
# "close":  assigns all minute volume to the close-price bin

# Rolling window (business days kept in merged view)
# Set to 90 for ~3M or 180 for ~6M
ROLLING_DAYS     = int(os.getenv("VOLUME_PROFILE_DAYS", "90"))

# Daemon cadence — hourly by default
POLL_INTERVAL_S  = float(os.getenv("VOLUME_PROFILE_POLL_S", "3600"))

# Redis
REDIS_HOST       = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT       = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB         = int(os.getenv("REDIS_DB", "0"))

# Keys / channels (unchanged schema)
CHANNEL          = os.getenv("VOLUME_PROFILE_CHANNEL", f"{SYMBOL}:chan:volume_profile")
KEY_3M           = os.getenv("VOLUME_PROFILE_KEY", f"{SYMBOL}:volume_profile:3m:json")
DAILY_PREFIX     = f"{SYMBOL}:volume_profile:by_day:"

# Market holidays (optional CSV: YYYY-MM-DD)
US_HOLIDAYS_ENV  = os.getenv("US_MARKET_HOLIDAYS", "")

# PID / logs
PIDFILE          = os.getenv("VOLUME_PROFILE_PIDFILE", f"/tmp/conv_vp.{SYMBOL}.pid")

# Networking / rate limit
RATE_SLEEP       = float(os.getenv("VOLUME_PROFILE_RATE_SLEEP", "0.4"))

# Behavior flags (code-driven)
AUTO_REINDEX_ON_META_MISMATCH = True
SCHEMA_VERSION = 1

# =========================
# Internals
# =========================
_stop_evt = Event()
_r: Optional[redis.Redis] = None
_sess: Optional[requests.Session] = None
_HOLIDAYS: Optional[set] = None

def _redis() -> redis.Redis:
    global _r
    if _r is None:
        _r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
    return _r

def _session() -> requests.Session:
    global _sess
    if _sess is None:
        s = requests.Session()
        s.headers.update({"Accept-Encoding": "gzip, deflate", "User-Agent": "vp-spy2spx/1.0"})
        adapter = requests.adapters.HTTPAdapter(pool_connections=16, pool_maxsize=32, max_retries=0)
        s.mount("https://", adapter); s.mount("http://", adapter)
        _sess = s
    return _sess

# =========================
# Market-day helpers
# =========================
def _load_holidays() -> set:
    global _HOLIDAYS
    if _HOLIDAYS is not None:
        return _HOLIDAYS
    out = set()
    if US_HOLIDAYS_ENV:
        for token in US_HOLIDAYS_ENV.split(","):
            t = token.strip()
            try:
                if t:
                    datetime.strptime(t, "%Y-%m-%d")
                    out.add(t)
            except Exception:
                pass
    _HOLIDAYS = out
    return _HOLIDAYS

def is_market_day(d: date) -> bool:
    if d.weekday() >= 5:  # Sat/Sun
        return False
    return d.strftime("%Y-%m-%d") not in _load_holidays()

def last_market_day(start: Optional[date] = None) -> date:
    d = start or datetime.now(timezone.utc).date()
    while not is_market_day(d):
        d -= timedelta(days=1)
    return d

# =========================
# Polygon helpers (minute bars)
# =========================
def _get_json(url: str, params: dict = None, timeout: int = 20) -> Optional[dict]:
    if _stop_evt.is_set():
        return None
    try:
        r = _session().get(url, params=params or {}, timeout=timeout)
        if r.status_code == 429:
            if _stop_evt.wait(RATE_SLEEP):
                return None
            return {"_rate_limit": True}
        if not r.ok:
            print(f"[http] {r.status_code} {url} params={params}")
            return None
        return r.json()
    except requests.RequestException as e:
        print(f"[net] {e}")
        return None

def fetch_minute_aggs_equity(ticker: str, from_ymd: str, to_ymd: str) -> List[dict]:
    """
    Streams all 1-minute bars between from_ymd..to_ymd (inclusive) for an equity.
    """
    url = f"{POLYGON_API}/v2/aggs/ticker/{ticker}/range/1/minute/{from_ymd}/{to_ymd}"
    params = {"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": POLYGON_API_KEY}
    out: List[dict] = []
    while not _stop_evt.is_set():
        j = _get_json(url, params=params)
        if j and j.get("_rate_limit"):
            continue
        if not j:
            break
        res = j.get("results") or []
        out.extend(res)
        nxt = j.get("next_url")
        if not nxt:
            break
        url = nxt
        params = None  # next_url already contains apiKey & params
    return out

# =========================
# Binning (SPY→SPX)
# =========================
def _round_to_bin_spy(price: float, bin_size: float) -> float:
    return round(math.floor(price / bin_size) * bin_size, 10)

def _spread_bins_spy(low_p: float, high_p: float, vol: float,
                     bin_size: float, buckets: defaultdict):
    if high_p < low_p:
        low_p, high_p = high_p, low_p
    start_bin = _round_to_bin_spy(low_p, bin_size)
    end_bin   = _round_to_bin_spy(high_p, bin_size)
    nbins = int(round((end_bin - start_bin) / bin_size)) + 1
    if nbins <= 0:
        return
    per_bin = vol / nbins
    b = start_bin
    for _ in range(nbins):
        buckets[b] += per_bin
        b = round(b + bin_size, 10)

def _spy_bins_to_spx_strikes(spy_buckets: Dict[float, float]) -> Dict[int, float]:
    """
    Convert SPY price bins (e.g., 662.34 with size 0.01) to SPX strikes (×10 → 6623).
    """
    out: Dict[int, float] = {}
    for spy_p, vol in spy_buckets.items():
        spx_k = int(round(spy_p * SPX_SCALE))  # 662.34*10 ≈ 6623
        out[spx_k] = out.get(spx_k, 0.0) + float(vol)
    return out

# =========================
# Daily build / store
# =========================
def _daily_key(ymd: str) -> str:
    return f"{DAILY_PREFIX}{ymd}"

def daily_profile_exists(ymd: str) -> bool:
    return _redis().exists(_daily_key(ymd)) == 1

def build_daily_profile_spy(ymd: str) -> Dict[int, float]:
    """
    Build SPX-per-strike volume profile for a single **business day** from SPY minute bars.
    """
    try:
        dt = datetime.strptime(ymd, "%Y-%m-%d").date()
    except Exception:
        return {}

    if not is_market_day(dt):
        print(f"[daily] {ymd} is not a market day → skip")
        return {}

    bars = fetch_minute_aggs_equity(SPY_TICKER, ymd, ymd)
    if _stop_evt.is_set():
        return {}
    if not bars:
        print(f"[daily] {ymd} no SPY bars")
        return {}

    buckets_spy = defaultdict(float)
    empties = 0
    for b in bars:
        v = b.get("v")
        if not isinstance(v, (int, float)) or v <= 0:
            empties += 1
            continue
        c = b.get("c"); h = b.get("h"); l = b.get("l")
        if BIN_MODE == "spread" and isinstance(h, (int, float)) and isinstance(l, (int, float)):
            _spread_bins_spy(float(l), float(h), float(v), BIN_SIZE_SPY, buckets_spy)
        else:
            if not isinstance(c, (int, float)):
                empties += 1
                continue
            bp = _round_to_bin_spy(float(c), BIN_SIZE_SPY)
            buckets_spy[bp] += float(v)

    if not buckets_spy:
        print(f"[daily] {ymd} → empty buckets after binning")
        return {}

    spx_buckets = _spy_bins_to_spx_strikes(buckets_spy)
    print(f"[daily] {ymd} bars={len(bars)} bins_spy={len(buckets_spy)} strikes_spx={len(spx_buckets)}")
    return spx_buckets

def store_daily_profile(ymd: str, strikes_to_vol: Dict[int, float], overwrite: bool = False) -> None:
    if _stop_evt.is_set():
        return
    if not strikes_to_vol or sum(strikes_to_vol.values()) <= 0.0:
        print(f"[store] {ymd} zero profile → skip")
        return
    key = _daily_key(ymd)
    r = _redis()
    if not overwrite and r.exists(key):
        print(f"[store] exists → {key} (skip)")
        return
    payload = {
        "symbol": SYMBOL,
        "date": ymd,
        "strikes": [{"price": int(k), "vol": float(v)} for k, v in sorted(strikes_to_vol.items())],
    }
    r.set(key, json.dumps(payload))
    print(f"[store] wrote {key} strikes={len(strikes_to_vol)}")

# =========================
# Rolling rebuild / publish
# =========================
def rebuild_rolling_profile(max_days: int = ROLLING_DAYS) -> Dict[str, object]:
    r = _redis()
    pattern = f"{DAILY_PREFIX}*"
    cursor = 0; keys: List[str] = []
    while True:
        cursor, batch = r.scan(cursor=cursor, match=pattern, count=300)
        keys.extend(batch)
        if cursor == 0:
            break

    # newest first
    dated: List[Tuple[date, str]] = []
    for k in keys:
        ymd = k.split(":")[-1]
        try:
            dt = datetime.strptime(ymd, "%Y-%m-%d").date()
            dated.append((dt, k))
        except Exception:
            pass
    dated.sort(reverse=True, key=lambda x: x[0])

    agg: Dict[int, float] = {}
    used_dates: List[str] = []

    def _num(x):
        return float(x) if isinstance(x, (int, float)) else None

    for dt0, key in dated[:max_days]:
        if _stop_evt.is_set():
            break
        raw = r.get(key)
        if not raw:
            continue
        try:
            j = json.loads(raw)
        except Exception:
            continue
        for item in j.get("strikes", []):
            # Accept both shapes: {"price": .., "vol": ..} OR {"k": .., "vol": ..} / {"v": ..}
            k_val = item.get("price", item.get("k"))
            v_val = item.get("vol", item.get("v"))
            if k_val is None or v_val is None:
                continue
            k_num = _num(k_val)
            v_num = _num(v_val)
            if k_num is None or v_num is None:
                continue
            k_int = int(round(k_num))
            agg[k_int] = agg.get(k_int, 0.0) + v_num
        used_dates.append(dt0.strftime("%Y-%m-%d"))

    buckets = [{"price": int(k), "vol": agg[k]} for k in sorted(agg.keys())]
    out = {
        "symbol": SYMBOL,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "window_days": max_days,
        "days_included": used_dates,
        "buckets": buckets,
        "meta": {
            "schema": SCHEMA_VERSION,
            "spy_ticker": SPY_TICKER,
            "bin_size_spy": BIN_SIZE_SPY,
            "spx_scale": SPX_SCALE,
            "mode": BIN_MODE,
        },
    }
    return out

def store_rolling_profile(profile: Dict[str, object]) -> None:
    if _stop_evt.is_set(): return
    _redis().set(KEY_3M, json.dumps(profile))
    print(f"[merge] wrote {KEY_3M} buckets={len(profile.get('buckets', []))}")

def publish_profile(profile: Dict[str, object]) -> None:
    if _stop_evt.is_set(): return
    msg = {"type": "volume_profile", "symbol": SYMBOL, "ts": profile.get("ts"), "key": KEY_3M}
    _redis().publish(CHANNEL, json.dumps(msg))
    print(f"[pubsub] {CHANNEL} ← {KEY_3M}")

# =========================
# Status helpers (for menu)
# =========================
def _list_daily_dates() -> List[str]:
    r = _redis()
    cursor = 0; keys: List[str] = []
    while True:
        cursor, batch = r.scan(cursor=cursor, match=f"{DAILY_PREFIX}*", count=300)
        keys.extend(batch)
        if cursor == 0:
            break
    dates = []
    for k in keys:
        try:
            dates.append(k.split(":")[-1])
        except Exception:
            pass
    dates = sorted(dates)
    return dates

def status_line() -> str:
    dates = _list_daily_dates()
    n = len(dates)
    span = f"{dates[0]} → {dates[-1]}" if n >= 2 else (dates[0] if n == 1 else "n/a")
    try:
        raw = _redis().get(KEY_3M)
        bcount = len((json.loads(raw) or {}).get("buckets", [])) if raw else 0
    except Exception:
        bcount = 0
    progress = f"Stored days: {n} ({span}). Buckets in merged: {bcount}."
    target = ROLLING_DAYS
    build = f"Building… {min(n, target)}/{target} days" if n < target else "Up to date"
    return f"      Status: {build}. {progress}"

# =========================
# Maintenance / reindex helpers
# =========================
def _merged_meta() -> Optional[dict]:
    try:
        raw = _redis().get(KEY_3M)
        if not raw:
            return None
        j = json.loads(raw)
        return j.get("meta")
    except Exception:
        return None

def _meta_mismatch(meta: Optional[dict]) -> bool:
    if not meta:
        return False
    try:
        return any([
            float(meta.get("bin_size_spy")) != float(BIN_SIZE_SPY),
            float(meta.get("spx_scale"))    != float(SPX_SCALE),
            str(meta.get("mode")).lower()   != str(BIN_MODE).lower(),
            int(meta.get("schema", 0))      != int(SCHEMA_VERSION),
            str(meta.get("spy_ticker"))     != str(SPY_TICKER),
        ])
    except Exception:
        return True

def purge_daily_profiles():
    r = _redis()
    cursor = 0
    n = 0
    pattern = f"{DAILY_PREFIX}*"
    while True:
        cursor, batch = r.scan(cursor=cursor, match=pattern, count=500)
        if batch:
            n += r.delete(*batch)
        if cursor == 0:
            break
    # also clear merged so consumers don't read stale meta
    r.delete(KEY_3M)
    print(f"[purge] removed {n} daily profiles and {KEY_3M}")

def _maybe_reindex_on_bin_change():
    if not AUTO_REINDEX_ON_META_MISMATCH:
        return
    meta = _merged_meta()
    if _meta_mismatch(meta):
        print("[reindex] meta change detected → purging & rebuilding with current settings "
              f"(bin={BIN_SIZE_SPY}, mode={BIN_MODE}, scale={SPX_SCALE})")
        purge_daily_profiles()
        backfill_last_n_days(ROLLING_DAYS, overwrite=True)

# =========================
# Orchestration
# =========================
def _choose_trade_date_for_today() -> str:
    return last_market_day().strftime("%Y-%m-%d")

def run_once(overwrite_today: bool = False):
    if not POLYGON_API_KEY:
        print("⚠️ POLYGON_API_KEY missing; cannot fetch.")
        return

    ymd = _choose_trade_date_for_today()
    if overwrite_today or not daily_profile_exists(ymd):
        pv = build_daily_profile_spy(ymd)
        if pv:
            store_daily_profile(ymd, pv, overwrite=overwrite_today)
        else:
            # walk back a few business days if today yielded nothing (holiday/early close)
            d = datetime.strptime(ymd, "%Y-%m-%d").date()
            for _ in range(5):
                d -= timedelta(days=1)
                while not is_market_day(d):
                    d -= timedelta(days=1)
                y = d.strftime("%Y-%m-%d")
                if daily_profile_exists(y) and not overwrite_today:
                    continue
                pv = build_daily_profile_spy(y)
                if pv:
                    store_daily_profile(y, pv, overwrite=overwrite_today)
                    break

    prof = rebuild_rolling_profile(ROLLING_DAYS)
    store_rolling_profile(prof)
    publish_profile(prof)
    try:
        print(status_line())
    except Exception:
        pass

def backfill_last_n_days(n: int = 90, overwrite: bool = False):
    """
    Backfill **business days**. Does not overwrite existing keys unless overwrite=True.
    Rebuilds & publishes the merged profile at the end.
    """
    d = last_market_day()
    filled = 0; seen = 0
    while filled < n and seen < n * 3 and not _stop_evt.is_set():
        ymd = d.strftime("%Y-%m-%d")
        if overwrite or not daily_profile_exists(ymd):
            pv = build_daily_profile_spy(ymd)
            if pv:
                store_daily_profile(ymd, pv, overwrite=overwrite)
                filled += 1
                print(f"[backfill] {ymd} strikes={len(pv)}")
            else:
                print(f"[backfill] {ymd} empty (skip)")
        seen += 1
        # prev business day
        d -= timedelta(days=1)
        while not is_market_day(d):
            d -= timedelta(days=1)

    prof = rebuild_rolling_profile(ROLLING_DAYS)
    store_rolling_profile(prof)
    publish_profile(prof)
    try:
        print(status_line())
    except Exception:
        pass
    print(f"[backfill] done. filled={filled}, scanned={seen}")

# =========================
# Daemon controls
# =========================
def _handle_stop(signum, frame):
    _stop_evt.set()
    print(f"[volume-profile] stop signal {signum}")

def is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0); return True
    except OSError:
        return False

def start_daemon():
    if os.path.exists(PIDFILE):
        print(f"[volume-profile] pidfile exists ({PIDFILE}); already running?")
    with open(PIDFILE, "w") as f:
        f.write(str(os.getpid()))
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT,  _handle_stop)
    print(f"[volume-profile] daemon start pid={os.getpid()} poll={int(POLL_INTERVAL_S)}s "
          f"(ticker={SPY_TICKER}, bin={BIN_SIZE_SPY} SPY, mode={BIN_MODE}, window={ROLLING_DAYS}d)")

    # Auto-reindex if existing meta disagrees with current settings
    _maybe_reindex_on_bin_change()

    while not _stop_evt.is_set():
        try:
            run_once(overwrite_today=False)
        except Exception as e:
            print(f"[volume-profile] loop error: {e}")
        # interruptible sleep
        if _stop_evt.wait(POLL_INTERVAL_S):
            break

    try:
        os.remove(PIDFILE)
    except Exception:
        pass
    print("[volume-profile] daemon stopped.")

def stop_daemon():
    if not os.path.exists(PIDFILE):
        print("[volume-profile] no pidfile; not running?"); return
    try:
        with open(PIDFILE, "r") as f:
            pid = int(f.read().strip())
    except Exception:
        print("[volume-profile] pidfile invalid.")
        try: os.remove(PIDFILE)
        except Exception: pass
        return
    try:
        os.kill(pid, signal.SIGTERM)
        print(f"[volume-profile] sent SIGTERM to {pid}")
        # wait ~5s for graceful exit
        for _ in range(50):
            if not is_pid_alive(pid): break
            time.sleep(0.1)
        else:
            print(f"[volume-profile] still running; SIGKILL {pid}")
            try: os.kill(pid, signal.SIGKILL)
            except ProcessLookupError: pass
    finally:
        try: os.remove(PIDFILE)
        except Exception: pass

def status_daemon():
    if not os.path.exists(PIDFILE):
        print("[volume-profile] NOT running (no pidfile).")
    else:
        try:
            with open(PIDFILE, "r") as f: pid = int(f.read().strip())
            if is_pid_alive(pid):
                print(f"[volume-profile] RUNNING (pid={pid})")
            else:
                print(f"[volume-profile] pidfile present but process {pid} not running.")
        except Exception:
            print("[volume-profile] pidfile invalid.")
    try:
        print(status_line())
    except Exception as e:
        print(f"      Status: (error) {e}")

# =========================
# CLI
# =========================
def main():
    import argparse
    p = argparse.ArgumentParser(description="Volume profile worker (SPY minute bars → SPX strikes)")
    p.add_argument("cmd", choices=["run-once", "start", "stop", "status", "backfill", "purge-daily"])
    p.add_argument("--days", type=int, default=90, help="business days to backfill (default 90)")
    p.add_argument("--overwrite", action="store_true", help="overwrite existing daily profiles")
    p.add_argument("--bin", type=float, help="force SPY bin size (e.g., 0.01 for ~1 SPX point)")
    p.add_argument("--mode", choices=["spread","close"], help="binning mode")
    args = p.parse_args()

    # Optional code-driven overrides (no envs needed)
    global BIN_SIZE_SPY, BIN_MODE
    if args.bin:
        BIN_SIZE_SPY = float(args.bin)
    if args.mode:
        BIN_MODE = args.mode

    if args.cmd == "run-once":
        run_once(overwrite_today=args.overwrite)
    elif args.cmd == "start":
        start_daemon()
    elif args.cmd == "stop":
        stop_daemon()
    elif args.cmd == "status":
        status_daemon()
    elif args.cmd == "backfill":
        backfill_last_n_days(args.days, overwrite=args.overwrite)
    elif args.cmd == "purge-daily":
        purge_daily_profiles()

if __name__ == "__main__":
    main()