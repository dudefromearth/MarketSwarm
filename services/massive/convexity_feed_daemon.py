#!/usr/bin/env python3
"""
convexity_feed_daemon.py — Control Center (Feed + API + SSE + Agent)  Py3.9+

Single entry point to:
  • Start/stop the FEED (Polygon → Redis) in foreground or daemon mode
  • Run feed once
  • Start/stop the API server (FastAPI/uvicorn)
  • Start/stop the SSE gateway (FastAPI/uvicorn) that streams Redis snapshots via /sse
  • Start/stop the Convexity Agent (digest generator) as a proper daemon
  • Health checks (Redis ping, pointers, freshness)
  • Tail logs
  • Start/stop the entire stack (Feed daemon + API + SSE + Agent + Volume Profile)
"""
import os, sys, json, time, hashlib, signal, argparse, subprocess, socket, importlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Tuple

import functools
print = functools.partial(print, flush=True)

import numpy as np
import requests
import redis

# ==========================
# CONFIG (Feed)
# ==========================
POLYGON_API = "https://api.polygon.io"
API_KEY = os.getenv("POLYGON_API_KEY", "R5TbDLsxMtu8vQvUlax8Af9tJwGevvOl")

# Use the index endpoint for SPX
API_SYMBOL    = os.getenv("API_SYMBOL", "I:SPX")   # index endpoint for Polygon API calls (we keep this)
SYMBOL        = os.getenv("SYMBOL", "SPX")         # display/Redis key

TOTAL_STRIKES = int(os.getenv("TOTAL_STRIKES", "100"))  # 0 = disable filtering
REDIS_HOST    = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT    = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB      = int(os.getenv("REDIS_DB", "0"))

TRAIL_TTL_SECONDS = int(os.getenv("TRAIL_TTL_SECONDS", "1200"))

# Throttle knobs for the loop
MODE        = os.getenv("MODE", "adaptive")  # "adaptive" or "max"
SLEEP_MIN_S = float(os.getenv("SLEEP_MIN_S", "0.03"))
SLEEP_MAX_S = float(os.getenv("SLEEP_MAX_S", "2.0"))
QUIET_DELTA = int(os.getenv("QUIET_DELTA", "10"))
HOT_DELTA   = int(os.getenv("HOT_DELTA", "100"))

# Publish even if chain diff == 0 when spot moves by at least this
SPOT_PUBLISH_EPS = float(os.getenv("SPOT_PUBLISH_EPS", "0.10"))  # index points

# Force periodic publish regardless of diff/spot (seconds); 0 disables
FORCE_PUBLISH_INTERVAL_S = float(os.getenv("FORCE_PUBLISH_INTERVAL_S", "2.0"))

# Prefer synthetic-from-chain for SPX spot. Set to "0" to revert to index-first.
USE_SYNTHETIC_FIRST = os.getenv("USE_SYNTHETIC_FIRST", "1") == "1"

# Snapshot mode: PRIMARY snapshot shape (API reads RAW regardless)
SNAPSHOT_MODE = os.getenv("SNAPSHOT_MODE", "minimal").lower()  # "minimal" or "full"

# Redis Pub/Sub + channels
USE_PUBSUB    = os.getenv("USE_PUBSUB", "1") == "1"
PUBSUB_PREFIX = os.getenv("PUBSUB_PREFIX", f"{SYMBOL}:chan")
FULL_CHANNEL  = os.getenv("FULL_CHANNEL", f"{PUBSUB_PREFIX}:full")
DIFF_CHANNEL  = os.getenv("DIFF_CHANNEL", f"{PUBSUB_PREFIX}:diff")

# Spot freshness knobs (only matter for fallback index bars)
LIVE_MAX_AGE_S    = int(os.getenv("LIVE_MAX_AGE_S", "90"))      # consider "live" if fresher than this
DELAYED_MAX_AGE_S = int(os.getenv("DELAYED_MAX_AGE_S", "1200")) # accept delayed bars up to 20 min

# Verbose spot-probe logging
VERBOSE_SPOT = os.getenv("VERBOSE_SPOT", "1") == "1"

# --- VIX config (always-on) ---
VIX_SYMBOL      = os.getenv("VIX_SYMBOL", "I:VIX")
VIX_KEY_LATEST  = "VIX:latest"
VIX_KEY_TRAIL   = "VIX:trail"
VIX_TRAIL_TTL   = 900  # 15 minutes
VIX_CHANNEL     = os.getenv("VIX_CHANNEL", "VIX:chan:full")
# -------------------------------

def store_vix_snapshot(vix_obj: dict):
    if not vix_obj:
        return
    r = _redis()
    ts_sec = vix_obj["ts_ms"] / 1000.0
    ts_iso = datetime.fromtimestamp(ts_sec, tz=timezone.utc).isoformat(timespec="seconds")
    out = {
        "symbol": "VIX",
        "value": vix_obj["value"],
        "ts": ts_iso,
        "source": vix_obj.get("source", "polygon/minute"),
        "api_symbol": vix_obj.get("api_symbol", VIX_SYMBOL),
    }
    payload = json.dumps(out)

    # store latest
    r.set(VIX_KEY_LATEST, payload)

    # store short trail
    try:
        r.zadd(VIX_KEY_TRAIL, {payload: ts_sec})
        r.zremrangebyscore(VIX_KEY_TRAIL, 0, ts_sec - VIX_TRAIL_TTL)
    except Exception:
        pass

    # publish for SSE
    if USE_PUBSUB:
        try:
            r.publish(VIX_CHANNEL, json.dumps({
                "type": "vix",
                "ts": ts_iso,
                "key": VIX_KEY_LATEST,
            }))
        except Exception:
            pass

    print(f"📈 VIX={out['value']:.2f}  ts={out['ts']}  -> {VIX_KEY_LATEST}")

# --- expiry fallback controls ---
EXPIRY_BACK_DAYS = int(os.getenv("EXPIRY_BACK_DAYS", "7"))    # search back this many days if today empty
EXPIRY_FWD_DAYS  = int(os.getenv("EXPIRY_FWD_DAYS", "3"))     # optionally look forward
PREFER_BACKFILL  = os.getenv("PREFER_BACKFILL", "1") == "1"   # prefer last available (Fri) over next (Mon)
TAG_BACKFILL     = os.getenv("TAG_BACKFILL", "1") == "1"      # annotate snapshots with is_backfill/is_lookahead

# Process controls
PIDFILE = os.getenv("PIDFILE", f"/tmp/convexity_feed_daemon.{SYMBOL}.pid")
LOGFILE = os.getenv("LOGFILE", f"/tmp/convexity_feed_daemon.{SYMBOL}.log")

# Paths / API launch config
BASE_DIR = Path(__file__).parent.resolve()
API_MODULE = "api:app"  # run via "python -m uvicorn api:app"
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))
API_RELOAD = os.getenv("API_RELOAD", "0") == "1"
RELOAD_INCLUDE = os.getenv("API_RELOAD_INCLUDE", "api.py")
RELOAD_EXCLUDE = os.getenv("API_RELOAD_EXCLUDE", "convexity_feed_daemon.py")

API_PIDFILE = os.getenv("API_PIDFILE", f"/tmp/fotw_api.{SYMBOL}.pid")
API_LOGFILE = os.getenv("API_LOGFILE",  f"/tmp/fotw_api.{SYMBOL}.log")

# --- SSE Gateway (FastAPI + Uvicorn) ---
SSE_HOST    = os.getenv("SSE_HOST", "0.0.0.0")
SSE_PORT    = int(os.getenv("SSE_PORT", "8010"))
SSE_MODULE  = "sse_gateway:app"
SSE_PIDFILE = os.getenv("SSE_PIDFILE", f"/tmp/convexity_sse.{SYMBOL}.pid")
SSE_LOGFILE = os.getenv("SSE_LOGFILE",  f"/tmp/convexity_sse.{SYMBOL}.log")

# --- Agent/VP launch helpers (their own background processes) ---
AGENT_LAUNCHER_PIDFILE = os.getenv("AGENT_LAUNCHER_PIDFILE", f"/tmp/convexity_agent_launcher.{SYMBOL}.pid")
AGENT_LOGFILE          = os.getenv("AGENT_LOGFILE",          f"/tmp/convexity_agent.{SYMBOL}.log")

VP_LAUNCHER_PIDFILE    = os.getenv("VP_LAUNCHER_PIDFILE",    f"/tmp/conv_vp_launcher.{SYMBOL}.pid")
VP_LAUNCHER_LOGFILE    = os.getenv("VP_LAUNCHER_LOGFILE",    f"/tmp/conv_vp_launcher.{SYMBOL}.log")

# Redis client (lazy)
_r = None

# ==========================
# Key Builder
# ==========================
class Keys:
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.latest_full      = f"{symbol}:latest_full"
        self.latest_full_raw  = f"{symbol}:latest_full_raw"
        self.latest_diff      = f"{symbol}:latest_diff"
        self.trail_full       = f"{symbol}:trail:full"
        self.trail_full_raw   = f"{symbol}:trail:full_raw"
        self.trail_diff       = f"{symbol}:trail:diff"

    def snapshot_key(self, ts_iso: str) -> str:
        return f"{self.symbol}:chain:{ts_iso}"

    def snapshot_raw_key(self, ts_iso: str) -> str:
        return f"{self.symbol}:chain_raw:{ts_iso}"

    def diff_key(self, ts_iso: str) -> str:
        return f"{self.symbol}:diff:{ts_iso}"

K = Keys(SYMBOL)

def rebuild_keys():
    global K
    K = Keys(SYMBOL)

# ==========================
# Helpers
# ==========================
def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def now_epoch() -> int:
    return int(datetime.now(timezone.utc).timestamp())

def mid(contract: dict) -> Optional[float]:
    q = contract.get("last_quote") or {}
    b, a = q.get("bid"), q.get("ask")
    try:
        return (b + a) / 2 if (b is not None and a is not None) else None
    except TypeError:
        return None

def _winsorized_median(values: List[float], pct: float = 0.1) -> Optional[float]:
    v = [x for x in values if isinstance(x, (int, float)) and np.isfinite(x)]
    if not v:
        return None
    v = sorted(v)
    n = len(v)
    k = int(max(0, min(n // 2, round(n * pct))))
    core = v[k:n - k] if n - 2 * k > 0 else v
    return float(np.median(core)) if core else None

# ---------- Polygon helpers ----------
def _poly_json(url: str, params: dict) -> Optional[dict]:
    try:
        r = requests.get(url, params=params, timeout=5)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None

def _get_prev_spot_from_redis() -> Optional[float]:
    try:
        r = _redis()
        ptr = r.get(K.latest_full_raw)
        if not ptr:
            return None
        raw = r.get(ptr)
        if not raw:
            return None
        j = json.loads(raw)
        spot = j.get("spot")
        if isinstance(spot, (int, float)) and spot > 0:
            return float(spot)
    except Exception:
        pass
    return None

def _get_index_minute(symbol_api: str) -> Tuple[Optional[float], Optional[int]]:
    """
    Return (close, t_ms) for latest minute bar if Polygon returns it.
    """
    url = f"{POLYGON_API}/v2/aggs/ticker/{symbol_api}/range/1/minute/2020-01-01/2100-01-01"
    j = _poly_json(url, {"adjusted": "true", "sort": "desc", "limit": 1, "apiKey": API_KEY})
    if j and isinstance(j.get("results"), list) and j["results"]:
        res = j["results"][0]
        c = res.get("c"); t = res.get("t")
        if isinstance(c, (int, float)) and isinstance(t, int):
            return float(c), int(t)
    return None, None

def _get_index_prev_close(symbol_api: str) -> Optional[float]:
    url = f"{POLYGON_API}/v2/aggs/ticker/{symbol_api}/prev"
    j = _poly_json(url, {"adjusted": "true", "apiKey": API_KEY})
    if j and isinstance(j.get("results"), list) and j["results"]:
        c = j["results"][0].get("c")
        if isinstance(c, (int, float)) and c > 0:
            return float(c)
    return None
# ---------- /Polygon helpers ----------

# ---------- Chain fetch with fallback (today/backfill/lookahead) ----------
def _fetch_chain_for_date(api_symbol: str, api_key: str, ymd: str) -> List[dict]:
    """
    Fetch snapshot chain for a specific expiration date (YYYY-MM-DD).
    Returns [] if Polygon has nothing for that date or on network hiccup.
    """
    url = (f"{POLYGON_API}/v3/snapshot/options/{api_symbol}"
           f"?expiration_date={ymd}&limit=250&include_greeks=true&apiKey={api_key}")
    out: List[dict] = []
    while url:
        try:
            resp = requests.get(url, timeout=8)
            if not resp.ok:
                return []
            j = resp.json()
        except Exception:
            return []
        out.extend(j.get("results", []))
        url = j.get("next_url")
        if url:
            join = "&" if "?" in url else "?"
            url = f"{url}{join}include_greeks=true&apiKey={api_key}"
    return out

def _ymd(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")

def fetch_best_chain_and_expiration(api_symbol: str, api_key: str) -> Tuple[List[dict], str, str]:
    """
    Try today's 0DTE first. If empty, search backward up to EXPIRY_BACK_DAYS
    for the most recent date with a non-empty chain (preferred).
    If still nothing, optionally look forward up to EXPIRY_FWD_DAYS.

    Returns (chain, expiration_ymd, mode) where mode ∈ {"today","backfill","lookahead","none"}.
    """
    now_utc = datetime.now(timezone.utc)
    today = _ymd(now_utc)

    # 1) Today
    chain = _fetch_chain_for_date(api_symbol, api_key, today)
    if chain:
        return chain, today, "today"

    # 2) Backfill / lookahead
    back_days = list(range(1, max(EXPIRY_BACK_DAYS, 0) + 1))
    fwd_days  = list(range(1, max(EXPIRY_FWD_DAYS, 0) + 1))

    def try_back():
        for d in back_days:
            ymd = _ymd(now_utc - timedelta(days=d))
            c = _fetch_chain_for_date(api_symbol, api_key, ymd)
            if c:
                return c, ymd, "backfill"
        return [], "", ""

    def try_fwd():
        for d in fwd_days:
            ymd = _ymd(now_utc + timedelta(days=d))
            c = _fetch_chain_for_date(api_symbol, api_key, ymd)
            if c:
                return c, ymd, "lookahead"
        return [], "", ""

    if PREFER_BACKFILL:
        c, ymd, mode = try_back()
        if c:
            return c, ymd, mode
        c, ymd, mode = try_fwd()
        if c:
            return c, ymd, mode
    else:
        c, ymd, mode = try_fwd()
        if c:
            return c, ymd, mode
        c, ymd, mode = try_back()
        if c:
            return c, ymd, mode

    return [], today, "none"
# ---------- /Chain fetch with fallback ----------

def estimate_spot_from_chain(chain: List[dict]) -> float:
    """
    Synthetic SPX via put-call parity around ATM:
      spot_k ≈ K + (C_mid - P_mid)
    """
    calls = {c["details"]["strike_price"]: mid(c)
             for c in chain if c["details"]["contract_type"] == "call" and mid(c) is not None}
    puts  = {p["details"]["strike_price"]: mid(p)
             for p in chain if p["details"]["contract_type"] == "put" and mid(p) is not None}
    Ks = sorted(set(calls).intersection(puts))
    if not Ks:
        raise ValueError("No overlapping call/put strikes with valid midprices to estimate spot.")
    syn_vals = [k + (calls[k] - puts[k]) for k in Ks]
    syn = _winsorized_median(syn_vals, pct=0.1)
    if syn is None:
        raise ValueError("Synthetic spot median failed.")
    return float(syn)

def filter_chain_around_spot(chain: List[dict], spot: float, total_strikes: int) -> List[dict]:
    if total_strikes <= 0:
        return chain
    strikes = sorted({c["details"]["strike_price"] for c in chain})
    if not strikes:
        return []
    atm = min(strikes, key=lambda x: abs(x - spot))
    idx = list(strikes).index(atm)
    half = total_strikes // 2
    lo, hi = max(0, idx - half), min(len(strikes), idx + half)
    window = set(strikes[lo:hi])
    return [c for c in chain if c["details"]["strike_price"] in window]

def comp_sig(contract: dict) -> str:
    q = contract.get("last_quote") or {}
    g = contract.get("greeks") or {}
    s = f'{q.get("bid")}:{q.get("ask")}:{g.get("delta")}:{g.get("gamma")}:{g.get("theta")}:{g.get("vega")}'
    return hashlib.blake2b(s.encode(), digest_size=12).hexdigest()

# ---------- SPOT ----------
def _spot_from_index(symbol_api: str) -> Tuple[Optional[float], str]:
    """Fallback: use Polygon index minute (live/delayed) then prev close."""
    now_ms = int(time.time() * 1000)
    c, t = _get_index_minute(symbol_api)
    if c is not None and t is not None:
        age_s = (now_ms - t) / 1000.0
        if age_s < LIVE_MAX_AGE_S:
            if VERBOSE_SPOT: print(f"[spot] minute_bar_live c={c:.2f} age={age_s:.1f}s")
            return c, "minute_bar_live"
        if age_s < DELAYED_MAX_AGE_S:
            if VERBOSE_SPOT: print(f"[spot] minute_bar_delayed c={c:.2f} age={age_s:.1f}s")
            return c, "minute_bar_delayed"
        if VERBOSE_SPOT: print(f"[spot] minute_bar STALE age={age_s:.1f}s")
    spx_prev = _get_index_prev_close(symbol_api)
    if isinstance(spx_prev, float):
        if VERBOSE_SPOT: print(f"[spot] prev_close {spx_prev:.2f}")
        return spx_prev, "prev_close"
    prev = _get_prev_spot_from_redis()
    if isinstance(prev, float):
        if VERBOSE_SPOT: print(f"[spot] prev_redis {prev:.2f}")
        return prev, "prev_redis"
    return None, "none"

def _derive_spot_synth_first(chain_all: List[dict], symbol_api: str) -> Tuple[Optional[float], str]:
    try:
        syn = estimate_spot_from_chain(chain_all)
        if VERBOSE_SPOT: print(f"[spot] synthetic_chain={syn:.2f}")
        return syn, "synthetic_chain"
    except Exception as e:
        if VERBOSE_SPOT: print(f"[spot] synthetic_chain failed: {e}")
    return _spot_from_index(symbol_api)

def _derive_spot_index_first(chain_all: List[dict], symbol_api: str) -> Tuple[Optional[float], str]:
    s, src = _spot_from_index(symbol_api)
    if isinstance(s, float) and s > 0:
        return s, src
    try:
        syn = estimate_spot_from_chain(chain_all)
        if VERBOSE_SPOT: print(f"[spot] synthetic_chain={syn:.2f}")
        return syn, "synthetic_chain"
    except Exception as e:
        if VERBOSE_SPOT: print(f"[spot] synthetic_chain failed: {e}")
    return None, "none"

def _derive_spot(chain_all: List[dict]) -> Tuple[Optional[float], str]:
    if USE_SYNTHETIC_FIRST:
        return _derive_spot_synth_first(chain_all, API_SYMBOL)
    else:
        return _derive_spot_index_first(chain_all, API_SYMBOL)
# ---------- /SPOT ----------

# --- VIX helpers (new) --------------------------------------
def fetch_vix_from_polygon(vix_symbol: str = VIX_SYMBOL) -> Optional[dict]:
    """
    Fetch latest VIX minute bar from Polygon.
    We model it after _get_index_minute but store structured JSON.
    """
    url = f"{POLYGON_API}/v2/aggs/ticker/{vix_symbol}/range/1/minute/2020-01-01/2100-01-01"
    j = _poly_json(url, {
        "adjusted": "true",
        "sort": "desc",
        "limit": 1,
        "apiKey": API_KEY,
    })
    if not j or not isinstance(j.get("results"), list) or not j["results"]:
        return None
    res = j["results"][0]
    val = res.get("c")
    ts  = res.get("t")
    if not isinstance(val, (int, float)) or not isinstance(ts, int):
        return None
    return {
        "symbol": "VIX",
        "value": float(val),
        "ts_ms": ts,
        "source": "polygon/minute",
        "api_symbol": vix_symbol,
    }

def store_vix_snapshot(vix_obj: dict):
    """
    Store VIX to its own keys:
      - VIX:latest  → JSON
      - VIX:trail   → zset, score=ts_sec, member=JSON
      - publish to VIX:chan:full so SSE can push it
    """
    if not vix_obj:
        return

    r = _redis()
    ts_sec = vix_obj["ts_ms"] / 1000.0
    ts_iso = datetime.fromtimestamp(ts_sec, tz=timezone.utc).isoformat(timespec="seconds")

    out = {
        "symbol": "VIX",
        "value": vix_obj["value"],
        "ts": ts_iso,
        "source": vix_obj.get("source", "polygon/minute"),
        "api_symbol": vix_obj.get("api_symbol", VIX_SYMBOL),
    }
    payload = json.dumps(out)

    # 1) latest
    r.set(VIX_KEY_LATEST, payload)

    # 2) short trail
    try:
        r.zadd(VIX_KEY_TRAIL, {payload: ts_sec})
        r.zremrangebyscore(VIX_KEY_TRAIL, 0, ts_sec - VIX_TRAIL_TTL)
    except Exception:
        pass

    # 3) **THIS** is what makes frontend see VIX
    if USE_PUBSUB:
        try:
            r.publish(
                VIX_CHANNEL,
                json.dumps({
                    "type": "vix",
                    "ts": ts_iso,
                    "key": VIX_KEY_LATEST,
                }),
            )
        except Exception:
            pass

    print(f"📈 VIX={out['value']:.2f}  ts={out['ts']}  -> {VIX_KEY_LATEST}")
# ------------------------------------------------------------
# ------------------------------------------------------------

# ==========================
# Mappers
# ==========================
def minimal_contract(c: dict) -> dict:
    d = c["details"]
    out = {"ticker": d["ticker"], "k": d["strike_price"], "cp": d["contract_type"]}
    q = c.get("last_quote") or {}
    g = c.get("greeks") or {}
    if (q.get("bid") is not None) or (q.get("ask") is not None):
        out["q"] = {k: q.get(k) for k in ("bid", "ask")}
    gg = {k: g.get(k) for k in ("delta", "gamma", "theta", "vega")}
    if not all(v is None for v in gg.values()):
        out["g"] = gg
    return out

def full_contract(c: dict) -> dict:
    d = c.get("details") or {}
    out = {
        "details": {
            "ticker": d.get("ticker"),
            "strike_price": d.get("strike_price"),
            "contract_type": d.get("contract_type"),
            "expiration_date": d.get("expiration_date"),
        },
        "last_quote": c.get("last_quote") or {},
        "last_trade": c.get("last_trade") or {},
        "greeks": c.get("greeks") or {},
        "volume": c.get("volume") or (c.get("day") or {}).get("volume"),
        "open_interest": c.get("open_interest"),
        "iv": c.get("iv") or c.get("implied_volatility"),
        "day": c.get("day"),
        "min": c.get("min"),
    }
    return {k: v for k, v in out.items() if v not in (None, {}, [])}

# ==========================
# Redis & timing utils
# ==========================
def _redis():
    global _r
    if _r is None:
        _r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
    return _r

def choose_sleep(delta_count: int) -> float:
    if MODE == "max":
        return SLEEP_MIN_S
    if delta_count >= HOT_DELTA:
        return SLEEP_MIN_S
    if delta_count <= QUIET_DELTA:
        return SLEEP_MAX_S
    span = max(HOT_DELTA - QUIET_DELTA, 1)
    frac = (delta_count - QUIET_DELTA) / span
    return max(SLEEP_MIN_S, min(SLEEP_MAX_S, SLEEP_MAX_S - (SLEEP_MAX_S - SLEEP_MIN_S) * frac))

def compute_diff(new_chain: List[dict],
                 prev_map: Dict[str, dict],
                 prev_hash: Dict[str, str]) -> dict:
    new_map  = {c["details"]["ticker"]: c for c in new_chain}
    new_set  = set(new_map.keys())
    new_hash = {t: comp_sig(new_map[t]) for t in new_set}
    prev_set = set(prev_map.keys())
    added   = list(new_set - prev_set)
    removed = list(prev_set - new_set)
    changed = [t for t in (new_set & prev_set) if new_hash[t] != prev_hash.get(t)]
    updates = [minimal_contract(new_map[t]) for t in changed]
    return {
        "added": added, "removed": removed, "updates": updates,
        "new_map": new_map, "new_hash": new_hash
    }

# ==========================
# Persistence (+ Pub/Sub)
# ==========================
def store_full_and_diff(ts_iso: str, exp_date: str, spot: float, spot_source: str,
                        primary_payload: List[dict], raw_payload: List[dict],
                        delta_count: int, added: List[str], removed: List[str], updates: List[dict]) -> None:
    r = _redis()
    ts_epoch = now_epoch()

    total_oi  = 0
    total_vol = 0
    for c in raw_payload:
        oi = c.get("open_interest")
        if isinstance(oi, (int, float)): total_oi += oi
        vol = c.get("volume")
        if isinstance(vol, (int, float)): total_vol += vol

    base = {
        "symbol":      SYMBOL,
        "api_symbol":  API_SYMBOL,
        "ts":          ts_iso,
        "expiration":  exp_date,
        "spot":        spot,
        "spot_source": spot_source,
        "total_open_interest": total_oi,
        "total_volume":        total_vol
    }

    # annotate backfill/lookahead
    if TAG_BACKFILL:
        try:
            today_ymd = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            base["is_backfill"]  = (exp_date < today_ymd)
            base["is_lookahead"] = (exp_date > today_ymd)
        except Exception:
            base["is_backfill"] = False
            base["is_lookahead"] = False

    primary_obj = dict(base, **{
        "count": len(primary_payload),
        "contracts": primary_payload,
        "mode": SNAPSHOT_MODE
    })
    raw_obj = dict(base, **{
        "count": len(raw_payload),
        "contracts": raw_payload
    })
    diff_obj = {
        "symbol": SYMBOL, "api_symbol": API_SYMBOL, "ts": ts_iso, "expiration": exp_date, "spot": spot,
        "diff_count": delta_count, "added": added, "removed": removed, "updates": updates
    }

    primary_key = K.snapshot_key(ts_iso)
    raw_key     = K.snapshot_raw_key(ts_iso)
    diff_key    = K.diff_key(ts_iso)

    pipe = r.pipeline(transaction=True)
    pipe.set(primary_key, json.dumps(primary_obj)); pipe.expire(primary_key, TRAIL_TTL_SECONDS)
    pipe.set(K.latest_full, primary_key);          pipe.zadd(K.trail_full,     {primary_key: ts_epoch})
    pipe.set(raw_key, json.dumps(raw_obj));        pipe.expire(raw_key,        TRAIL_TTL_SECONDS)
    pipe.set(K.latest_full_raw, raw_key);          pipe.zadd(K.trail_full_raw, {raw_key: ts_epoch})
    pipe.set(diff_key, json.dumps(diff_obj));      pipe.expire(diff_key,       TRAIL_TTL_SECONDS)
    pipe.set(K.latest_diff, diff_key);             pipe.zadd(K.trail_diff,     {diff_key: ts_epoch})
    pipe.execute()

    if USE_PUBSUB:
        try:
            r.publish(FULL_CHANNEL, json.dumps({
                "type": "full","symbol": SYMBOL,"api_symbol": API_SYMBOL,"ts": ts_iso,
                "key": primary_key,"count": len(primary_payload),
                "total_volume": total_vol,"total_oi": total_oi,"mode": SNAPSHOT_MODE
            }))
            r.publish(DIFF_CHANNEL, json.dumps({
                "type": "diff","symbol": SYMBOL,"api_symbol": API_SYMBOL,"ts": ts_iso,
                "key": diff_key,"diff_count": delta_count,
                "added": len(added),"removed": len(removed),"updated": len(updates)
            }))
        except Exception as e:
            print(f"⚠️  Pub/Sub publish error: {e}")

    print(
        f"✅ {SYMBOL} ({API_SYMBOL}) {ts_iso} | spot={spot:.2f} src={spot_source} | "
        f"mode={SNAPSHOT_MODE} | primary={len(primary_payload)} raw={len(raw_payload)} | "
        f"totVol={total_vol} totOI={total_oi} | Δ={delta_count} "
        f"(+{len(added)} / ~{len(updates)} / -{len(removed)})"
    )

# ==========================
# Run Loop / One-shot (Feed)
# ==========================
_running = True

def _handle_stop(signum, frame):
    global _running
    _running = False
    print(f"🛑 Received signal {signum}, shutting down...")

def _build_payloads(chain: List[dict]) -> Tuple[List[dict], List[dict]]:
    raw_payload = [full_contract(c) for c in chain]           # always full
    primary = raw_payload if SNAPSHOT_MODE == "full" else [minimal_contract(c) for c in chain]
    return primary, raw_payload

def _derive_spot_wrapper(chain_all: List[dict]) -> Tuple[Optional[float], str]:
    return _derive_spot(chain_all)

def run_once() -> int:
    if not API_KEY:
        raise EnvironmentError("Set POLYGON_API_KEY in your environment.")
    prev_map: Dict[str, dict] = {}
    prev_hash: Dict[str, str] = {}

    ts = iso_now()
    chain_all, exp, mode_exp = fetch_best_chain_and_expiration(API_SYMBOL, API_KEY)
    if not chain_all:
        print("[heartbeat] no chain found today/nearby; attempting spot-only heartbeat publish.")
        spot, spot_src = _derive_spot_wrapper([])
        if isinstance(spot, float) and spot > 0:
            primary, raw = _build_payloads([])
            store_full_and_diff(ts, exp, spot, spot_src, primary, raw, 0, [], [], [])
        # --- also try VIX once here ---
        v = fetch_vix_from_polygon()
        if v:
            store_vix_snapshot(v)
        return 0

    if mode_exp != "today":
        print(f"[expiry] using {mode_exp} chain for {exp}")

    spot, spot_src = _derive_spot_wrapper(chain_all)
    if not (isinstance(spot, float) and spot > 0):
        print("⚠️ spot derivation failed; skipping publish this cycle")
        # still try VIX
        v = fetch_vix_from_polygon()
        if v:
            store_vix_snapshot(v)
        return 0

    chain = filter_chain_around_spot(chain_all, spot, TOTAL_STRIKES)
    diff = compute_diff(chain, prev_map, prev_hash)
    delta_count = len(diff["added"]) + len(diff["removed"]) + len(diff["updates"])

    primary, raw = _build_payloads(chain)
    store_full_and_diff(ts, exp, spot, spot_src, primary, raw, delta_count,
                        diff["added"], diff["removed"], diff["updates"])

    # --- VIX fetch/store as part of run-once too ---
    v = fetch_vix_from_polygon()
    if v:
        store_vix_snapshot(v)

    return delta_count

def run_loop() -> None:
    if not API_KEY:
        raise EnvironmentError("Set POLYGON_API_KEY in your environment.")

    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT,  _handle_stop)

    prev_map: Dict[str, dict] = {}
    prev_hash: Dict[str, str] = {}
    last_spot_published: Optional[float] = None
    last_publish_at: float = 0.0

    while _running:
        try:
            ts = iso_now()

            chain_all, exp, mode_exp = fetch_best_chain_and_expiration(API_SYMBOL, API_KEY)
            if not chain_all:
                print("[heartbeat] chain empty → publishing spot-only snapshot if available.")
                spot, spot_src = _derive_spot_wrapper([])
                if isinstance(spot, float) and spot > 0:
                    primary, raw = _build_payloads([])
                    store_full_and_diff(ts, exp, spot, spot_src, primary, raw, 0, [], [], [])
                else:
                    print("⚠️ no spot available from index fallback either.")
                # even if chain empty, still try to pull VIX
                v = fetch_vix_from_polygon()
                if v:
                    store_vix_snapshot(v)
                time.sleep(SLEEP_MAX_S)
                continue

            if mode_exp != "today":
                print(f"[expiry] using {mode_exp} chain for {exp}")

            spot, spot_src = _derive_spot_wrapper(chain_all)
            if not (isinstance(spot, float) and spot > 0):
                print("⚠️ spot derivation failed; skipping publish this cycle")
                # but we still poll VIX
                v = fetch_vix_from_polygon()
                if v:
                    store_vix_snapshot(v)
                time.sleep(0.5)
                continue

            chain = filter_chain_around_spot(chain_all, spot, TOTAL_STRIKES)
            diff = compute_diff(chain, prev_map, prev_hash)
            delta_count = len(diff["added"]) + len(diff["removed"]) + len(diff["updates"])

            now = time.time()
            force_due = (FORCE_PUBLISH_INTERVAL_S > 0) and ((now - last_publish_at) >= FORCE_PUBLISH_INTERVAL_S)

            should_publish = (delta_count > 0) \
                             or (last_spot_published is None) \
                             or (abs(spot - last_spot_published) >= SPOT_PUBLISH_EPS) \
                             or force_due

            if should_publish:
                primary, raw = _build_payloads(chain)
                store_full_and_diff(ts, exp, spot, spot_src, primary, raw, delta_count,
                                    diff["added"], diff["removed"], diff["updates"])
                last_spot_published = spot
                last_publish_at = now

                # --- pull VIX right when we push SPX ---
                v = fetch_vix_from_polygon()
                if v:
                    store_vix_snapshot(v)

            else:
                # even on quiet ticks, we can sample VIX but less often
                v = fetch_vix_from_polygon()
                if v:
                    store_vix_snapshot(v)

            prev_map  = diff["new_map"]
            prev_hash = diff["new_hash"]

            time.sleep(choose_sleep(delta_count))
        except Exception as e:
            print(f"⚠️  {e}")
            time.sleep(0.5)

# ==========================
# Daemonization (POSIX double-fork)
# ==========================
def _daemonize(stdout_path: str, stderr_path: str):
    pid = os.fork()
    if pid > 0:
        os._exit(0)
    os.setsid()
    os.umask(0)

    pid = os.fork()
    if pid > 0:
        os._exit(0)

    os.environ["PYTHONUNBUFFERED"] = "1"
    try:
        sys.stdout.flush(); sys.stderr.flush()
    except Exception:
        pass

    si = open(os.devnull, "r")
    so = open(stdout_path, "a")
    se = open(stderr_path, "a")
    os.dup2(si.fileno(), 0); os.dup2(so.fileno(), 1); os.dup2(se.fileno(), 2)
    try:
        sys.stdout = open(stdout_path, "a", buffering=1)
        sys.stderr = open(stderr_path, "a", buffering=1)
    except Exception:
        pass

def write_pidfile():
    with open(PIDFILE, "w") as f:
        f.write(str(os.getpid()))
    print(f"🟢 daemon started (pid={os.getpid()})  pidfile={PIDFILE}  log={LOGFILE}")

def read_pidfile() -> Optional[int]:
    if not os.path.exists(PIDFILE): return None
    try:
        with open(PIDFILE, "r") as f:
            return int(f.read().strip())
    except Exception:
        return None

def remove_pidfile():
    try:
        if os.path.exists(PIDFILE):
            os.remove(PIDFILE)
    except Exception:
        pass

def is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False

# ==========================
# Port / process helpers (API & SSE)
# ==========================
def _is_port_open(host: str, port: int, timeout: float = 0.25) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        try:
            s.connect((host, port))
            return True
        except Exception:
            return False

def _popen_background(cmd_list, pidfile, logfile):
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    os.makedirs(os.path.dirname(logfile), exist_ok=True)
    logf = open(logfile, "a+", buffering=1)
    proc = subprocess.Popen(
        cmd_list,
        stdout=logf, stderr=logf,
        stdin=subprocess.DEVNULL,
        cwd=str(BASE_DIR),
        start_new_session=True,
        close_fds=True,
        env=env
    )
    with open(pidfile, "w") as f:
        f.write(str(proc.pid))
    print(f"spawned: {' '.join(cmd_list)}  (pid={proc.pid})  log={logfile}  pidfile={pidfile}")
    return proc.pid

def start_api_server():
    pid = None
    if os.path.exists(API_PIDFILE):
        try:
            with open(API_PIDFILE, "r") as f:
                pid = int(f.read().strip())
        except Exception:
            pid = None
    if pid and is_pid_alive(pid):
        print(f"api: already RUNNING (pid {pid})")
        return pid
    if _is_port_open("127.0.0.1", API_PORT):
        print(f"api: port {API_PORT} is already in use — not starting another instance.")
        return None

    args = [sys.executable, "-m", "uvicorn", API_MODULE, "--host", API_HOST, "--port", str(API_PORT)]
    if API_RELOAD:
        args += ["--reload", "--reload-include", RELOAD_INCLUDE, "--reload-exclude", RELOAD_EXCLUDE]
    pid = _popen_background(args, API_PIDFILE, API_LOGFILE)

    for _ in range(50):
        if _is_port_open("127.0.0.1", API_PORT):
            print(f"api: READY on http://{API_HOST}:{API_PORT}")
            break
        time.sleep(0.1)
    return pid

def stop_api_server():
    pid = None
    if os.path.exists(API_PIDFILE):
        try:
            with open(API_PIDFILE, "r") as f:
                pid = int(f.read().strip())
        except Exception:
            pid = None
    if not pid:
        print("api: no pidfile or invalid pidfile.")
        return
    try:
        os.kill(pid, signal.SIGTERM)
        print(f"api: sent SIGTERM to pid {pid}")
        for _ in range(50):
            if not is_pid_alive(pid):
                break
            time.sleep(0.1)
    except ProcessLookupError:
        print(f"api: process {pid} not found.")
    except Exception as e:
        print(f"api: stop error: {e}")
    try:
        os.remove(API_PIDFILE)
    except Exception:
        pass

def status_api():
    pid=None
    if os.path.exists(API_PIDFILE):
        try:
            with open(API_PIDFILE, "r") as f:
                pid=int(f.read().strip())
        except Exception:
            pid=None
    listening = _is_port_open("127.0.0.1", API_PORT)
    if pid and is_pid_alive(pid):
        print(f"api: RUNNING (pid {pid})  pidfile={API_PIDFILE}  port={'open' if listening else 'closed'}")
    else:
        print(f"api: NOT running. port={'open' if listening else 'closed'}")

# --- SSE Gateway controls ---
def start_sse_gateway():
    pid = None
    if os.path.exists(SSE_PIDFILE):
        try:
            with open(SSE_PIDFILE, "r") as f:
                pid = int(f.read().strip())
        except Exception:
            pid = None
    if pid and is_pid_alive(pid):
        print(f"sse: already RUNNING (pid {pid})")
        return pid
    if _is_port_open("127.0.0.1", SSE_PORT):
        print(f"sse: port {SSE_PORT} is already in use — not starting another instance.")
        return None

    args = [sys.executable, "-m", "uvicorn", SSE_MODULE, "--host", SSE_HOST, "--port", str(SSE_PORT)]
    pid = _popen_background(args, SSE_PIDFILE, SSE_LOGFILE)

    for _ in range(50):
        if _is_port_open("127.0.0.1", SSE_PORT):
            print(f"sse: READY on http://{SSE_HOST}:{SSE_PORT}")
            break
        time.sleep(0.1)
    return pid

def stop_sse_gateway():
    pid = None
    if os.path.exists(SSE_PIDFILE):
        try:
            with open(SSE_PIDFILE, "r") as f:
                pid = int(f.read().strip())
        except Exception:
            pid = None
    if not pid:
        print("sse: no pidfile or invalid pidfile.")
        return
    try:
        os.kill(pid, signal.SIGTERM)
        print(f"sse: sent SIGTERM to pid {pid}")
        for _ in range(50):
            if not is_pid_alive(pid): break
            time.sleep(0.1)
    except ProcessLookupError:
        print(f"sse: process {pid} not found.")
    except Exception as e:
        print(f"sse: stop error: {e}")
    try:
        os.remove(SSE_PIDFILE)
    except Exception:
        pass

def status_sse():
    pid = None
    if os.path.exists(SSE_PIDFILE):
        try:
            with open(SSE_PIDFILE, "r") as f:
                pid = int(f.read().strip())
        except Exception:
            pid = None
    listening = _is_port_open("127.0.0.1", SSE_PORT)
    if pid and is_pid_alive(pid):
        print(f"sse: RUNNING (pid {pid})  pidfile={SSE_PIDFILE}  port={'open' if listening else 'closed'}")
    else:
        print(f"sse: NOT running. port={'open' if listening else 'closed'}")

# --- Convexity Agent controls (run as background process) ---
def _agent_mod():
    return importlib.import_module("convexity_agent_worker")

def run_convexity_once():
    _agent_mod().run_once()

def start_convexity_agent_daemon():
    """
    Launch agent in its own background process so the menu isn't blocked.
    Uses a tiny Python -c shim that calls agent.start_agent_daemon().
    The agent worker should manage its own PID internally.
    """
    # If a launcher is already present, avoid duplicates.
    if os.path.exists(AGENT_LAUNCHER_PIDFILE):
        try:
            with open(AGENT_LAUNCHER_PIDFILE, "r") as f:
                pid = int(f.read().strip())
            if is_pid_alive(pid):
                print(f"[agent] launcher already RUNNING (pid {pid})")
                return
        except Exception:
            pass
    code = "import convexity_agent_worker as m; m.start_agent_daemon()"
    cmd = [sys.executable, "-c", code]
    _popen_background(cmd, AGENT_LAUNCHER_PIDFILE, AGENT_LOGFILE)

def stop_convexity_agent_daemon():
    # ask the worker to stop its own daemon
    cmd = [sys.executable, "-c", "import convexity_agent_worker as m; m.stop_agent_daemon()"]
    subprocess.run(cmd, check=False)
    # cleanup launcher pidfile if present
    try:
        if os.path.exists(AGENT_LAUNCHER_PIDFILE):
            with open(AGENT_LAUNCHER_PIDFILE, "r") as f:
                pid = int(f.read().strip())
            if is_pid_alive(pid):
                # best-effort: send SIGTERM to the launcher if it's still around
                try:
                    os.kill(pid, signal.SIGTERM)
                except Exception:
                    pass
            os.remove(AGENT_LAUNCHER_PIDFILE)
    except Exception:
        pass
    print("[agent] stop requested")

def status_convexity_agent():
    # delegate to worker's status
    cmd = [sys.executable, "-c", "import convexity_agent_worker as m; m.status_agent_daemon()"]
    subprocess.run(cmd, check=False)

# --- Volume Profile controls (run as background process) ---
def run_volume_profile_once():
    import volume_profile_worker as vpw
    vpw.run_once()

def start_volume_profile_daemon():
    """
    Run the volume_profile_worker as a separate background process.
    Its 'start' subcommand runs a foreground loop; we detach it here.
    """
    # avoid duplicate launcher
    if os.path.exists(VP_LAUNCHER_PIDFILE):
        try:
            with open(VP_LAUNCHER_PIDFILE, "r") as f:
                pid = int(f.read().strip())
            if is_pid_alive(pid):
                print(f"[volume-profile] launcher already RUNNING (pid {pid})")
                return
        except Exception:
            pass
    script = str((Path(__file__).parent / "volume_profile_worker.py").resolve())
    cmd = [sys.executable, script, "start"]
    _popen_background(cmd, VP_LAUNCHER_PIDFILE, VP_LAUNCHER_LOGFILE)

def stop_volume_profile_daemon():
    script = str((Path(__file__).parent / "volume_profile_worker.py").resolve())
    subprocess.run([sys.executable, script, "stop"], check=False)
    try:
        if os.path.exists(VP_LAUNCHER_PIDFILE):
            with open(VP_LAUNCHER_PIDFILE, "r") as f:
                pid = int(f.read().strip())
            if is_pid_alive(pid):
                try:
                    os.kill(pid, signal.SIGTERM)
                except Exception:
                    pass
            os.remove(VP_LAUNCHER_PIDFILE)
    except Exception:
        pass
    print("[volume-profile] stop requested")

def status_volume_profile_daemon():
    script = str((Path(__file__).parent / "volume_profile_worker.py").resolve())
    subprocess.run([sys.executable, script, "status"], check=False)

# ==========================
# Stack helpers (menu-safe)
# ==========================
def start_feed_daemon_via_cli():
    cur = read_pidfile()
    if cur and is_pid_alive(cur):
        print("Feed already running."); return
    cmd = [sys.executable, str(Path(__file__).resolve()), "start", "--daemon"]
    print(f"[stack] launching feed daemon: {' '.join(cmd)}")
    env = os.environ.copy()
    env["FORCE_DAEMON"] = "1"
    subprocess.Popen(
        cmd,
        cwd=str(BASE_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
        env=env
    )
    for _ in range(50):
        pid = read_pidfile()
        if pid and is_pid_alive(pid):
            print(f"[stack] feed RUNNING (pid {pid})")
            break
        time.sleep(0.1)

def stop_feed_daemon_via_cli():
    pid = read_pidfile()
    if not pid or not is_pid_alive(pid):
        print("Feed not running."); return
    os.kill(pid, signal.SIGTERM)
    print(f"Feed: sent SIGTERM to pid {pid}")
    # wait up to ~5s for graceful exit; escalate if needed
    for _ in range(50):
        if not is_pid_alive(pid):
            break
        time.sleep(0.1)
    else:
        print(f"Feed: still running; sending SIGKILL to {pid}")
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    remove_pidfile()

# ==========================
# Health check
# ==========================
def health_check(symbol: str):
    print("\n--- Health Check ---")
    try:
        r = _redis()
        pong = r.ping()
        print(f"Redis: {'OK' if pong else 'FAIL'} ({REDIS_HOST}:{REDIS_PORT}/{REDIS_DB})")
    except Exception as e:
        print(f"Redis: FAIL ({e})"); return

    latest_ptr = r.get(f"{symbol}:latest_full_raw")
    if latest_ptr:
        print(f"latest_full_raw → {latest_ptr}")
        raw = r.get(latest_ptr)
        if raw:
            try:
                j = json.loads(raw)
                ts = j.get("ts")
                exp = j.get("expiration")
                spot = j.get("spot")
                spot_src = j.get("spot_source")
                count = j.get("count")
                age = None
                if ts:
                    try:
                        dtz = datetime.fromisoformat(ts.replace("Z","+00:00"))
                        age = int((datetime.now(timezone.utc) - dtz).total_seconds())
                    except Exception:
                        age = None
                print(f"RAW snapshot: ts={ts} age={age if age is not None else 'n/a'}s exp={exp} spot={spot} src={spot_src} count={count}")
            except Exception as e:
                print(f"RAW snapshot: bad JSON: {e}")
        else:
            print("RAW snapshot: key missing/expired.")
    else:
        print(f"Pointer missing: {symbol}:latest_full_raw")

    # show VIX too if present
    try:
        v = r.get(VIX_KEY_LATEST)
        if v:
            print(f"VIX: {v}")
        else:
            print("VIX: no latest value")
    except Exception:
        print("VIX: error reading from Redis")

    print(f"API URL (if running): http://{API_HOST}:{API_PORT}/api/mode/{symbol}\n")

# ==========================
# Utils
# ==========================
def tail_log(path: str):
    try:
        print(f"--- tailing {path} (Ctrl+C to exit) ---")
        if not os.path.exists(path):
            print("(no log yet)")
        last_size = 0
        while True:
            try:
                if os.path.exists(path):
                    size = os.path.getsize(path)
                    if size < last_size:
                        last_size = 0
                    with open(path, "r", buffering=1) as f:
                        f.seek(last_size)
                        chunk = f.read()
                        if chunk:
                            print(chunk, end="")
                        last_size = size
            except FileNotFoundError:
                pass
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[tail stopped]")

def show_config():
    print("\nCurrent configuration:")
    print(f"  SYMBOL (Redis)    = {SYMBOL}")
    print(f"  API_SYMBOL (HTTP) = {API_SYMBOL}")
    print(f"  TOTAL_STRIKES     = {TOTAL_STRIKES}")
    print(f"  SNAPSHOT_MODE     = {SNAPSHOT_MODE}   (PRIMARY snapshot)")
    print(f"  RAW SNAPSHOT      = always (key suffix: _raw)")
    print(f"  MODE              = {MODE}")
    print(f"  SLEEP_MIN_S       = {SLEEP_MIN_S}")
    print(f"  SLEEP_MAX_S       = {SLEEP_MAX_S}")
    print(f"  QUIET_DELTA       = {QUIET_DELTA}")
    print(f"  HOT_DELTA         = {HOT_DELTA}")
    print(f"  TRAIL_TTL_SECONDS = {TRAIL_TTL_SECONDS}")
    print(f"  USE_PUBSUB        = {USE_PUBSUB}  (full={FULL_CHANNEL}, diff={DIFF_CHANNEL})")
    print(f"  REDIS_HOST:PORT   = {REDIS_HOST}:{REDIS_PORT} (db={REDIS_DB})")
    print(f"  PIDFILE           = {PIDFILE}")
    print(f"  LOGFILE           = {LOGFILE}")
    print(f"  API_PIDFILE       = {API_PIDFILE}")
    print(f"  API_LOGFILE       = {API_LOGFILE}")
    print(f"  SSE_PIDFILE       = {SSE_PIDFILE}")
    print(f"  SSE_LOGFILE       = {SSE_LOGFILE}\n")
    print("Key patterns:")
    print(f"  PRIMARY snapshot  = {SYMBOL}:chain:<ISO>")
    print(f"  RAW snapshot      = {SYMBOL}:chain_raw:<ISO>")
    print(f"  DIFF              = {SYMBOL}:diff:<ISO>")
    print(f"  Pointers          = {K.latest_full}, {K.latest_full_raw}, {K.latest_diff}")
    print(f"  Trails            = {K.trail_full}, {K.trail_full_raw}, {K.trail_diff}\n")
    print(f"  VIX latest        = {VIX_KEY_LATEST}")
    print(f"  VIX trail (zset)  = {VIX_KEY_TRAIL}\n")
    print(f"API: host={API_HOST} port={API_PORT} reload={API_RELOAD} include='{RELOAD_INCLUDE}' exclude='{RELOAD_EXCLUDE}'")
    print(f"SSE: host={SSE_HOST} port={SSE_PORT} module='{SSE_MODULE}'")

# --- Volume Profile status helpers (menu display) --------------------
VP_ROLLING_DAYS = int(os.getenv("VOLUME_PROFILE_DAYS", "90"))
VP_KEY_3M = os.getenv("VOLUME_PROFILE_KEY", f"{SYMBOL}:volume_profile:3m:json")

def _count_vp_days(symbol: str) -> int:
    """How many daily volume-profile docs do we have in Redis?"""
    r = _redis()
    cursor = 0
    total = 0
    pattern = f"{symbol}:volume_profile:by_day:*"
    while True:
        cursor, batch = r.scan(cursor=cursor, match=pattern, count=200)
        total += len(batch)
        if cursor == 0:
            break
    return total

def _sum_vp_total_volume() -> Optional[float]:
    """
    Sum total volume across the current rolling window buckets.
    Returns float or None if missing.
    """
    try:
        r = _redis()
        raw = r.get(VP_KEY_3M)
        if not raw:
            return None
        j = json.loads(raw)
        buckets = j.get("buckets") or []
        return float(sum(b.get("vol", 0.0) for b in buckets if isinstance(b.get("vol"), (int, float))))
    except Exception:
        return None

def _human_short(n: float) -> str:
    """Compact human formatting (K/M/B/T)."""
    if n is None:
        return "n/a"
    neg = n < 0
    n = abs(n)
    for unit in ("", "K", "M", "B", "T"):
        if n < 1000.0:
            return f"{'-' if neg else ''}{n:,.0f}{unit}"
        n /= 1000.0
    return f"{'-' if neg else ''}{n:,.0f}P"

def _vp_status_details() -> str:
    """
    Detailed line showing days stored, target, first/last day, and total 3m volume.
    """
    try:
        r = _redis()
        raw = r.get(VP_KEY_3M)
        days_have = _count_vp_days(SYMBOL)
        target = VP_ROLLING_DAYS
        if not raw:
            return f"      Status: no rolling profile yet. Days={days_have}/{target}"

        j = json.loads(raw)
        days_included = j.get("days_included") or []
        first_day = days_included[-1] if days_included else "n/a"
        last_day  = days_included[0]  if days_included else "n/a"
        tot = _sum_vp_total_volume()
        tot_txt = _human_short(tot) if isinstance(tot, (int, float)) else "n/a"
        status = "Up to date" if days_have >= target else f"Building… {days_have}/{target} days"
        return f"      Status: {status}. Window: {first_day} → {last_day}. 3m total vol: {tot_txt}"
    except Exception as e:
        return f"      Status: (error reading) {e}"

def tail_volume_profile_log():
    tail_log(VP_LAUNCHER_LOGFILE)
# ---------------------------------------------------------------------

# ==========================
# Interactive Menu
# ==========================
def _safe_input(prompt: str) -> Optional[str]:
    try:
        return input(prompt)
    except EOFError:
        print("\n[input closed: EOF] Exiting menu.")
        return None
    except KeyboardInterrupt:
        print("\n[Ctrl+C] Exiting menu.")
        return None

def _show_vix_latest_from_redis():
    r = _redis()
    v = r.get(VIX_KEY_LATEST)
    if not v:
        print("VIX: no latest value in Redis.")
        return
    try:
        j = json.loads(v)
    except Exception:
        print(f"VIX (raw): {v}")
        return
    print("VIX latest:")
    print(f"  symbol: {j.get('symbol')}")
    print(f"  value : {j.get('value')}")
    print(f"  ts    : {j.get('ts')}")
    print(f"  src   : {j.get('source')}")
    print(f"  api   : {j.get('api_symbol')}")

def run_menu():
    while True:
        print("\n=== Convexity Control Center ===")
        print("Feed:")
        print("  1) Start feed (foreground)")
        print("  2) Start feed (daemon)")
        print("  3) Stop feed daemon")
        print("  4) Feed status")
        print("  5) Run feed once")
        print("")
        print("API server (FastAPI + Uvicorn):")
        print("  6) Start API server")
        print("  7) Stop API server")
        print("  8) API status")
        print("")
        print("Stack:")
        print("  9)  Start FULL stack (API + feed daemon + SSE + Agent + VP)")
        print("  10) Stop  FULL stack (VP + Agent + feed + SSE + API)")
        print("")
        print("Tools:")
        print("  11) Tail FEED log")
        print("  12) Tail API log")
        print("  13) Show config")
        print("  14) Health check")
        print("  15) Toggle SNAPSHOT_MODE (minimal/full)")
        print("")
        print("SSE gateway:")
        print("  16) Start SSE gateway")
        print("  17) Stop SSE gateway")
        print("  18) SSE status")
        print("  19) Tail SSE log")
        print("")
        print("Convexity Agent:")
        print("  20) Run Convexity once (generate digest now)")
        print("  21) Start Convexity agent daemon")
        print("  22) Stop Convexity agent daemon")
        print("  23) Convexity agent status")
        print("")
        print("VIX:")
        print("  24) Show VIX latest (from Redis)")
        print("")
        print("Volume Profile:")
        print("  25) Run volume-profile once")
        print("  26) Start volume-profile daemon")
        print("  27) Stop volume-profile daemon")
        print("  28) Volume-profile status")
        print("  29) Tail volume-profile log")
        # live progress/summary line (detailed)
        try:
            print(_vp_status_details())
        except Exception as e:
            print(f"      Status: (error reading) {e}")
        print("")
        print("  q) Quit")

        s = _safe_input("> ")
        if s is None:
            return
        choice = s.strip().lower()

        if choice == "1":
            print("Starting feed in foreground. Ctrl+C to stop.")
            run_loop()

        elif choice == "2":
            start_feed_daemon_via_cli()

        elif choice == "3":
            stop_feed_daemon_via_cli()

        elif choice == "4":
            pid = read_pidfile()
            if pid and is_pid_alive(pid):
                print(f"Feed: RUNNING (pid {pid})  pidfile={PIDFILE}  log={LOGFILE}")
            else:
                print("Feed: NOT running.")

        elif choice == "5":
            d = run_once()
            print(f"run-once complete; diff_count={d}")

        elif choice == "6":
            start_api_server()

        elif choice == "7":
            stop_api_server()

        elif choice == "8":
            status_api()

        elif choice == "9":
            # Start FULL stack: API + Feed daemon + SSE + Agent daemon + Volume-Profile daemon
            status_api()
            start_api_server()
            start_feed_daemon_via_cli()
            start_sse_gateway()
            try:
                start_convexity_agent_daemon()
            except Exception as e:
                print(f"[stack] agent start error: {e}")
            try:
                start_volume_profile_daemon()
            except Exception as e:
                print(f"[stack] volume-profile start error: {e}")
            print("[stack] FULL stack requested. Returning to menu…")

        elif choice == "10":
            # Stop FULL stack: VP + Agent + Feed + SSE + API (in this order)
            try:
                stop_volume_profile_daemon()
            except Exception as e:
                print(f"[stack] volume-profile stop error: {e}")
            try:
                stop_convexity_agent_daemon()
            except Exception as e:
                print(f"[stack] agent stop error: {e}")
            stop_feed_daemon_via_cli()
            stop_sse_gateway()
            stop_api_server()
            print("[stack] FULL stack stopped.")

        elif choice == "11":
            tail_log(LOGFILE)

        elif choice == "12":
            tail_log(API_LOGFILE)

        elif choice == "13":
            show_config()

        elif choice == "14":
            health_check(SYMBOL)

        elif choice == "15":
            global SNAPSHOT_MODE
            SNAPSHOT_MODE = "full" if SNAPSHOT_MODE == "minimal" else "minimal"
            print(f"SNAPSHOT_MODE set to: {SNAPSHOT_MODE} (API reads RAW; this only changes PRIMARY payload)")

        elif choice == "16":
            start_sse_gateway()

        elif choice == "17":
            stop_sse_gateway()

        elif choice == "18":
            status_sse()

        elif choice == "19":
            tail_log(SSE_LOGFILE)

        elif choice == "20":
            print("[agent] running once now…")
            run_convexity_once()
            print("[agent] done.")

        elif choice == "21":
            print("[agent] starting daemon…")
            start_convexity_agent_daemon()

        elif choice == "22":
            print("[agent] stopping daemon…")
            stop_convexity_agent_daemon()

        elif choice == "23":
            status_convexity_agent()

        elif choice == "24":
            _show_vix_latest_from_redis()

        elif choice == "25":
            print("[volume-profile] running once…")
            run_volume_profile_once()
            print("[volume-profile] done.")

        elif choice == "26":
            print("[volume-profile] starting daemon…")
            start_volume_profile_daemon()

        elif choice == "27":
            print("[volume-profile] stopping daemon…")
            stop_volume_profile_daemon()

        elif choice == "28":
            status_volume_profile_daemon()
            try:
                print(_vp_status_details())
            except Exception:
                pass

        elif choice == "29":
            tail_volume_profile_log()

        elif choice == "30":
            os.system("python volume_profile_worker.py backfill --days 90 --overwrite")

        elif choice == "31":
            os.system("python volume_profile_worker.py purge-daily")

        elif choice in ("q","quit","exit"):
            # NOTE: Quit only exits the menu now — background daemons keep running.
            print("Goodbye.")
            return

        else:
            print("Unknown choice.")

# ==========================
# CLI
# ==========================
def main_cli():
    parser = argparse.ArgumentParser(description="Convexity Feed Daemon (0DTE → Redis) + Control Center")
    sub = parser.add_subparsers(dest="cmd")

    p_start = sub.add_parser("start", help="Start continuous feed")
    p_start.add_argument("--daemon", action="store_true", help="Run in background (POSIX)")
    p_start.add_argument("--snapshot-mode", choices=["minimal","full"], help="Override SNAPSHOT_MODE for this run")
    p_start.add_argument("--symbol", help="Redis/display symbol (e.g., SPX)")
    p_start.add_argument("--api-symbol", help='API symbol for Polygon (e.g., "I:SPX" or "SPX")')

    sub.add_parser("stop", help="Stop daemon via PID file")
    sub.add_parser("status", help="Show daemon status")

    p_once = sub.add_parser("run-once", help="Run one feed cycle and exit")
    p_once.add_argument("--snapshot-mode", choices=["minimal","full"], help="Override SNAPSHOT_MODE for this run")
    p_once.add_argument("--symbol", help="Redis/display symbol (e.g., SPX)")
    p_once.add_argument("--api-symbol", help='API symbol for Polygon (e.g., "I:SPX" or "SPX")')

    sub.add_parser("menu", help="Open interactive control center")

    args = parser.parse_args()

    # Fallback if invoked without proper subcommand from a detached session
    if os.getenv("FORCE_DAEMON") == "1" and (args.cmd is None):
        class _Shim: pass
        s = _Shim()
        s.daemon = True
        s.snapshot_mode = None
        s.symbol = None
        s.api_symbol = None
        args.cmd = "start"
        args = argparse.Namespace(**vars(args), **vars(s))

    global SNAPSHOT_MODE, SYMBOL, API_SYMBOL, PIDFILE, LOGFILE, API_PIDFILE, API_LOGFILE, SSE_PIDFILE, SSE_LOGFILE
    if getattr(args, "snapshot_mode", None):
        SNAPSHOT_MODE = args.snapshot_mode
    if getattr(args, "symbol", None):
        SYMBOL = args.symbol
        rebuild_keys()
        if os.getenv("PIDFILE") is None:
            PIDFILE = f"/tmp/convexity_feed_daemon.{SYMBOL}.pid"
        if os.getenv("LOGFILE") is None:
            LOGFILE = f"/tmp/convexity_feed_daemon.{SYMBOL}.log"
        if os.getenv("API_PIDFILE") is None:
            API_PIDFILE = f"/tmp/fotw_api.{SYMBOL}.pid"
        if os.getenv("API_LOGFILE") is None:
            API_LOGFILE = f"/tmp/fotw_api.{SYMBOL}.log"
        if os.getenv("SSE_PIDFILE") is None:
            SSE_PIDFILE = f"/tmp/convexity_sse.{SYMBOL}.pid"
        if os.getenv("SSE_LOGFILE") is None:
            SSE_LOGFILE  = f"/tmp/convexity_sse.{SYMBOL}.log"
    if getattr(args, "api_symbol", None):
        API_SYMBOL = args.api_symbol

    if args.cmd is None and not sys.stdin.isatty():
        print("No TTY detected and no subcommand provided; exiting instead of opening menu.")
        sys.exit(2)

    if args.cmd is None or args.cmd == "menu":
        run_menu(); return

    if args.cmd == "start":
        if args.daemon:
            pid = read_pidfile()
            if pid and is_pid_alive(pid):
                print("Already running."); return
            if not API_KEY:
                raise EnvironmentError("Set POLYGON_API_KEY in your environment.")
            os.environ["PYTHONUNBUFFERED"] = "1"
            _daemonize(LOGFILE, LOGFILE)
            write_pidfile()
            try:
                run_loop()
            finally:
                remove_pidfile()
        else:
            print("Starting in foreground. Press Ctrl+C to stop.")
            run_loop()

    elif args.cmd == "stop":
        pid = read_pidfile()
        if not pid:
            print("No PID file; daemon not running?"); return
        os.kill(pid, signal.SIGTERM)
        print(f"Sent SIGTERM to pid {pid}.")
        for _ in range(30):
            if not is_pid_alive(pid): break
            time.sleep(0.2)
        else:
            print(f"Still running; sending SIGKILL to {pid}")
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        remove_pidfile()

    elif args.cmd == "status":
        pid = read_pidfile()
        if pid and is_pid_alive(pid):
            print(f"Running (pid {pid})  pidfile={PIDFILE}  log={LOGFILE}")
        else:
            print("Not running.")

    elif args.cmd == "run-once":
        delta = run_once()
        print(f"run-once complete; diff_count={delta}")

if __name__ == "__main__":
    main_cli()