#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
dte_feed_worker.py — SPX multi-DTE feed (Polygon → Redis), VIX included.

• Maintains legacy 0DTE keys (SPX:*), trails, and pub/sub (compat for your UI)
• Adds parallel per-expiry namespaces: SPX:EXP:<YYYY-MM-DD>:*
• Optional DTE alias pointers:      SPX:DTE:<n>:*
• Publishes FULL + DIFF (always for 0DTE; optionally for all expiries)
• Spot from Massive index snapshot via get_spot (single spot per sweep)
• Cadence: adaptive (no fixed 30s), with FORCE_PUBLISH_INTERVAL_S

Configuration is driven by:

  • configure_from_dict(config: dict)  # orchestrator path
  • configure_from_env()              # CLI / legacy path

No API keys or shell-script values are hardcoded; defaults are safe and inert.
"""

from __future__ import annotations

import os
import sys
import time
import json
import random
import signal
import hashlib
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta, timezone

import numpy as np  # currently unused but harmless
import requests
import redis

import get_spot as massive_spot  # Massive spot helper module

# ==========================
# CONFIG (defaults; override via configure_from_dict / configure_from_env)
# ==========================

# Polygon / Markets options API
POLYGON_API = "https://api.polygon.io"
API_KEY = ""  # Polygon API key: must be provided via config or env

# Underlyings
API_SYMBOL = "I:SPX"   # index symbol for Polygon endpoints and Massive
SYMBOL = "SPX"         # Redis/display symbol (legacy namespace base)

# DTEs to poll
DTE_LIST: List[int] = [0, 1, 2, 3, 4, 5]

# Redis
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB   = 0

# Trails horizon (for trail_* sorted sets, not for payload TTL)
TRAIL_TTL_SECONDS = 1200

# Snapshot TTL (how long a given chain/diff payload key stays alive)
# Default: 3 days, so we survive weekends/holidays.
SNAPSHOT_TTL_SECONDS = 3 * 24 * 3600

# Publish cadence
SPOT_PUBLISH_EPS = 0.10
FORCE_PUBLISH_INTERVAL_S = 2.0

# Adaptive sleep
SLEEP_MIN_S = 0.05
SLEEP_MAX_S = 1.0
QUIET_DELTA = 10
HOT_DELTA   = 100

# Snapshot mode for PRIMARY payload (API always reads RAW)
SNAPSHOT_MODE = "minimal"  # minimal|full

# Pub/Sub
USE_PUBSUB    = True
PUBSUB_PREFIX = f"{SYMBOL}:chan"
FULL_CHANNEL  = f"{PUBSUB_PREFIX}:full"
DIFF_CHANNEL  = f"{PUBSUB_PREFIX}:diff"

# Per-expiry pubsub (optional; default off)
USE_EXP_PUBSUB = False

# VIX
VIX_SYMBOL      = "I:VIX"
VIX_KEY_LATEST  = "VIX:latest"
VIX_KEY_TRAIL   = "VIX:trail"
VIX_TRAIL_TTL   = 900
VIX_CHANNEL     = "VIX:chan:full"

# Diffs for all expiries?
DIFF_FOR_ALL    = True

# DTE alias pointers (SPX:DTE:<n>:*)
USE_DTE_ALIASES = True

# HTTP / pagination (Polygon options)
REQUEST_TIMEOUT = 12
PAGE_LIMIT      = 250
INCLUDE_GREEKS  = True

# Expiry tagging
TAG_BACKFILL = True

# Massive spot config (driven by orchestrator/env)
# These are pushed into the get_spot module via _apply_massive_config()
MASSIVE_API_KEY = ""         # if empty, get_spot will use its own env-based API_KEY
MASSIVE_SNAPSHOT_URL = ""    # optional override for get_spot.BASE_URL

# ==========================
# Redis / Keys
# ==========================

_r = None  # redis client (lazy)

def _redis():
    global _r
    if _r is None:
        _r = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            decode_responses=True,
        )
    return _r


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def now_epoch() -> int:
    return int(datetime.now(timezone.utc).timestamp())


class Keys:
    """Legacy 0DTE namespace (unchanged structurally)."""
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


class ExpKeys:
    """Per-expiry parallel namespace."""
    def __init__(self, symbol: str, exp_ymd: str):
        base = f"{symbol}:EXP:{exp_ymd}"
        self.base = base
        self.latest_full     = f"{base}:latest_full"
        self.latest_full_raw = f"{base}:latest_full_raw"
        self.latest_diff     = f"{base}:latest_diff"
        self.trail_full      = f"{base}:trail:full"
        self.trail_full_raw  = f"{base}:trail:full_raw"
        self.trail_diff      = f"{base}:trail:diff"

    def snapshot_key(self, ts_iso: str) -> str:
        return f"{self.base}:chain:{ts_iso}"

    def snapshot_raw_key(self, ts_iso: str) -> str:
        return f"{self.base}:chain_raw:{ts_iso}"

    def diff_key(self, ts_iso: str) -> str:
        return f"{self.base}:diff:{ts_iso}"


class MultiKeys:
    """Combined multi-DTE namespace (all expiries in DTE_LIST)."""
    def __init__(self, symbol: str):
        base = f"{symbol}_MULTI"
        self.base = base
        self.latest_full      = f"{base}:latest_full"
        self.latest_full_raw  = f"{base}:latest_full_raw"
        self.latest_diff      = f"{base}:latest_diff"
        self.trail_full       = f"{base}:trail:full"
        self.trail_full_raw   = f"{base}:trail:full_raw"
        self.trail_diff       = f"{base}:trail:diff"

    def snapshot_key(self, ts_iso: str) -> str:
        return f"{self.base}:chain:{ts_iso}"

    def snapshot_raw_key(self, ts_iso: str) -> str:
        return f"{self.base}:chain_raw:{ts_iso}"

    def diff_key(self, ts_iso: str) -> str:
        return f"{self.base}:diff:{ts_iso}"


def dte_alias_keys(symbol: str, dte: int):
    """Alias pointer namespace: SPX:DTE:<n>:* (only pointers, not payloads)."""
    class D: ...
    o = D()
    base = f"{symbol}:DTE:{dte}"
    o.latest_full     = f"{base}:latest_full"
    o.latest_full_raw = f"{base}:latest_full_raw"
    o.latest_diff     = f"{base}:latest_diff"
    return o


# These are initialized once configuration is known
K_legacy: Optional[Keys] = None
K_multi: Optional[MultiKeys] = None

# ==========================
# Config wiring helpers
# ==========================

def _as_bool(val: Any, default: bool) -> bool:
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    return str(val).strip().lower() in ("1", "true", "yes", "on")


def _apply_massive_config():
    """
    Push MASSIVE_* settings into the get_spot module so it doesn't depend on process env.
    """
    # Update module-level globals in get_spot
    if MASSIVE_API_KEY:
        massive_spot.API_KEY = MASSIVE_API_KEY
    if MASSIVE_SNAPSHOT_URL:
        massive_spot.BASE_URL = MASSIVE_SNAPSHOT_URL


def configure_from_dict(cfg: Dict[str, Any]) -> None:
    """
    Configure the worker from a flat config dict (orchestrator path).

    Expected keys (all optional, defaults preserved if missing):

      api_key, polygon_api_key,
      api_symbol, symbol, dte_list,
      redis_host, redis_port, redis_db,
      trail_ttl_seconds, snapshot_ttl_seconds,
      spot_publish_eps, force_publish_interval_s,
      sleep_min_s, sleep_max_s, quiet_delta, hot_delta,
      snapshot_mode,
      use_pubsub, pubsub_prefix, full_channel, diff_channel,
      use_exp_pubsub,
      vix_symbol, vix_key_latest, vix_key_trail, vix_trail_ttl, vix_channel,
      diff_for_all, use_dte_aliases,
      request_timeout, page_limit, include_greeks,
      tag_backfill,
      massive_api_key, massive_snapshot_url
    """
    global API_KEY, API_SYMBOL, SYMBOL, DTE_LIST
    global REDIS_HOST, REDIS_PORT, REDIS_DB
    global TRAIL_TTL_SECONDS, SNAPSHOT_TTL_SECONDS
    global SPOT_PUBLISH_EPS, FORCE_PUBLISH_INTERVAL_S
    global SLEEP_MIN_S, SLEEP_MAX_S, QUIET_DELTA, HOT_DELTA
    global SNAPSHOT_MODE
    global USE_PUBSUB, PUBSUB_PREFIX, FULL_CHANNEL, DIFF_CHANNEL, USE_EXP_PUBSUB
    global VIX_SYMBOL, VIX_KEY_LATEST, VIX_KEY_TRAIL, VIX_TRAIL_TTL, VIX_CHANNEL
    global DIFF_FOR_ALL, USE_DTE_ALIASES
    global REQUEST_TIMEOUT, PAGE_LIMIT, INCLUDE_GREEKS
    global TAG_BACKFILL
    global MASSIVE_API_KEY, MASSIVE_SNAPSHOT_URL
    global K_legacy, K_multi, _r

    # --- API / symbols (Polygon) ---
    if "api_key" in cfg:
        API_KEY = str(cfg["api_key"] or "")
    if "polygon_api_key" in cfg:
        API_KEY = str(cfg["polygon_api_key"] or API_KEY)

    if "api_symbol" in cfg:
        API_SYMBOL = str(cfg["api_symbol"])
    if "symbol" in cfg:
        SYMBOL = str(cfg["symbol"])

    # --- DTE list ---
    dte_src = cfg.get("dte_list")
    if dte_src is not None:
        if isinstance(dte_src, (list, tuple)):
            DTE_LIST = [int(x) for x in dte_src]
        else:
            parts = str(dte_src).split(",")
            DTE_LIST = [int(x.strip()) for x in parts if x.strip()]

    # --- Redis ---
    if "redis_host" in cfg:
        REDIS_HOST = str(cfg["redis_host"])
    if "redis_port" in cfg:
        REDIS_PORT = int(cfg["redis_port"])
    if "redis_db" in cfg:
        REDIS_DB = int(cfg["redis_db"])

    # --- TTLs / cadence ---
    if "trail_ttl_seconds" in cfg:
        TRAIL_TTL_SECONDS = int(cfg["trail_ttl_seconds"])
    if "snapshot_ttl_seconds" in cfg:
        SNAPSHOT_TTL_SECONDS = int(cfg["snapshot_ttl_seconds"])
    if "spot_publish_eps" in cfg:
        SPOT_PUBLISH_EPS = float(cfg["spot_publish_eps"])
    if "force_publish_interval_s" in cfg:
        FORCE_PUBLISH_INTERVAL_S = float(cfg["force_publish_interval_s"])
    if "sleep_min_s" in cfg:
        SLEEP_MIN_S = float(cfg["sleep_min_s"])
    if "sleep_max_s" in cfg:
        SLEEP_MAX_S = float(cfg["sleep_max_s"])
    if "quiet_delta" in cfg:
        QUIET_DELTA = int(cfg["quiet_delta"])
    if "hot_delta" in cfg:
        HOT_DELTA = int(cfg["hot_delta"])

    # --- snapshot mode ---
    if "snapshot_mode" in cfg:
        SNAPSHOT_MODE = str(cfg["snapshot_mode"]).lower()

    # --- Pub/Sub ---
    if "use_pubsub" in cfg:
        USE_PUBSUB = _as_bool(cfg["use_pubsub"], USE_PUBSUB)
    PUBSUB_PREFIX = str(cfg.get("pubsub_prefix", f"{SYMBOL}:chan"))
    FULL_CHANNEL  = str(cfg.get("full_channel", f"{PUBSUB_PREFIX}:full"))
    DIFF_CHANNEL  = str(cfg.get("diff_channel", f"{PUBSUB_PREFIX}:diff"))

    if "use_exp_pubsub" in cfg:
        USE_EXP_PUBSUB = _as_bool(cfg["use_exp_pubsub"], USE_EXP_PUBSUB)

    # --- VIX ---
    if "vix_symbol" in cfg:
        VIX_SYMBOL = str(cfg["vix_symbol"])
    if "vix_key_latest" in cfg:
        VIX_KEY_LATEST = str(cfg["vix_key_latest"])
    if "vix_key_trail" in cfg:
        VIX_KEY_TRAIL = str(cfg["vix_key_trail"])
    if "vix_trail_ttl" in cfg:
        VIX_TRAIL_TTL = int(cfg["vix_trail_ttl"])
    if "vix_channel" in cfg:
        VIX_CHANNEL = str(cfg["vix_channel"])

    # --- diffs / aliases ---
    if "diff_for_all" in cfg:
        DIFF_FOR_ALL = _as_bool(cfg["diff_for_all"], DIFF_FOR_ALL)
    if "use_dte_aliases" in cfg:
        USE_DTE_ALIASES = _as_bool(cfg["use_dte_aliases"], USE_DTE_ALIASES)

    # --- HTTP / Polygon options ---
    if "request_timeout" in cfg:
        REQUEST_TIMEOUT = int(cfg["request_timeout"])
    if "page_limit" in cfg:
        PAGE_LIMIT = int(cfg["page_limit"])
    if "include_greeks" in cfg:
        INCLUDE_GREEKS = _as_bool(cfg["include_greeks"], INCLUDE_GREEKS)

    if "tag_backfill" in cfg:
        TAG_BACKFILL = _as_bool(cfg["tag_backfill"], TAG_BACKFILL)

    # --- Massive (spot) ---
    if "massive_api_key" in cfg:
        MASSIVE_API_KEY = str(cfg["massive_api_key"] or "")
    if "massive_snapshot_url" in cfg:
        MASSIVE_SNAPSHOT_URL = str(cfg["massive_snapshot_url"] or MASSIVE_SNAPSHOT_URL)

    _apply_massive_config()

    # --- Derived key namespaces ---
    K_legacy = Keys(SYMBOL)
    K_multi  = MultiKeys(SYMBOL)

    # Reset Redis client so it reconnects with new host/port/db if changed
    _r = None


def configure_from_env() -> None:
    """
    Legacy/CLI config bridge: build a small cfg dict from environment vars,
    then delegate to configure_from_dict.
    """
    cfg: Dict[str, Any] = {}

    ak = os.getenv("POLYGON_API_KEY")
    if ak:
        cfg["api_key"] = ak

    api_symbol = os.getenv("API_SYMBOL")
    if api_symbol:
        cfg["api_symbol"] = api_symbol

    symbol = os.getenv("SYMBOL")
    if symbol:
        cfg["symbol"] = symbol

    dte_env = os.getenv("DTE_LIST")
    if dte_env:
        cfg["dte_list"] = dte_env

    rh = os.getenv("REDIS_HOST")
    if rh:
        cfg["redis_host"] = rh
    rp = os.getenv("REDIS_PORT")
    if rp:
        cfg["redis_port"] = int(rp)
    rdb = os.getenv("REDIS_DB")
    if rdb:
        cfg["redis_db"] = int(rdb)

    # Optional tunables
    for env_key, cfg_key, cast in [
        ("TRAIL_TTL_SECONDS", "trail_ttl_seconds", int),
        ("SNAPSHOT_TTL_SECONDS", "snapshot_ttl_seconds", int),
        ("SPOT_PUBLISH_EPS", "spot_publish_eps", float),
        ("FORCE_PUBLISH_INTERVAL_S", "force_publish_interval_s", float),
        ("SLEEP_MIN_S", "sleep_min_s", float),
        ("SLEEP_MAX_S", "sleep_max_s", float),
        ("QUIET_DELTA", "quiet_delta", int),
        ("HOT_DELTA", "hot_delta", int),
        ("SNAPSHOT_MODE", "snapshot_mode", str),
        ("USE_PUBSUB", "use_pubsub", str),
        ("USE_EXP_PUBSUB", "use_exp_pubsub", str),
        ("DIFF_FOR_ALL", "diff_for_all", str),
        ("USE_DTE_ALIASES", "use_dte_aliases", str),
        ("REQUEST_TIMEOUT", "request_timeout", int),
        ("PAGE_LIMIT", "page_limit", int),
        ("INCLUDE_GREEKS", "include_greeks", str),
        ("TAG_BACKFILL", "tag_backfill", str),
        # Massive
        ("MASSIVE_API_KEY", "massive_api_key", str),
        ("MASSIVE_SNAPSHOT_URL", "massive_snapshot_url", str),
    ]:
        v = os.getenv(env_key)
        if v is not None:
            cfg[cfg_key] = cast(v)

    configure_from_dict(cfg)

# ==========================
# HTTP helpers (Polygon options)
# ==========================

class HttpError(RuntimeError):
    pass


def _http_get(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    p = dict(params or {})
    if API_KEY:
        p["apiKey"] = API_KEY
    attempt = 0
    while True:
        attempt += 1
        r = requests.get(url, params=p, timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            try:
                return r.json()
            except Exception:
                raise HttpError(f"Bad JSON from {r.url}")
        if r.status_code in (429, 500, 502, 503, 504) and attempt <= 4:
            delay = 0.3 * (2 ** (attempt - 1)) + random.random() * 0.25
            print(f"    ↻ {r.status_code} {r.reason}; retrying in {delay:.2f}s …")
            time.sleep(delay)
            continue
        try:
            err = r.json()
        except Exception:
            err = r.text
        raise HttpError(f"HTTP {r.status_code} from {r.url} -> {err}")

# ==========================
# Polygon option snapshots
# ==========================

def _expiries_for(dtes: List[int]) -> List[str]:
    today = datetime.now(timezone.utc).date()
    return [(today + timedelta(days=d)).isoformat() for d in dtes]


def _paginate_snapshot_expiration(underlying: str, expiration: str) -> List[Dict[str, Any]]:
    """
    IMPORTANT:
    • Polygon wants include_greeks=true for greeks; 'include=greeks,iv' is NOT honored here.
    • Use API_SYMBOL (e.g., 'I:SPX') for index options.
    """
    url = f"{POLYGON_API}/v3/snapshot/options/{underlying}"
    params = {
        "expiration_date": expiration,
        "limit": PAGE_LIMIT,
    }
    if INCLUDE_GREEKS:
        params["include_greeks"] = "true"
        params["include"] = "greeks,iv"  # harmless extra param
    all_rows: List[dict] = []
    while True:
        data = _http_get(url, params)
        rows = data.get("results") or []
        all_rows.extend(rows)
        next_url = data.get("next_url")
        if not next_url:
            break
        url = next_url
        params = {}
    return all_rows

# ==========================
# VIX (via Massive get_spot)
# ==========================

def fetch_vix_from_massive() -> Optional[dict]:
    """
    Fetch VIX spot from Massive using get_spot, then normalize into the
    same object shape store_vix_snapshot expects.
    """
    index_symbol = VIX_SYMBOL  # e.g. "I:VIX"
    try:
        spot = massive_spot.get_spot(index_symbol, api_key=MASSIVE_API_KEY or None)
    except Exception as e:
        print(f"  ⚠️ Massive VIX spot fetch failed for {index_symbol}: {e}")
        return None

    ts_ms = int(time.time() * 1000)
    return {
        "symbol": "VIX",
        "value": float(spot),
        "ts_ms": ts_ms,
        "source": "massive/snapshot",
        "api_symbol": index_symbol,
    }


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
        "source": vix_obj.get("source", "massive/snapshot"),
        "api_symbol": vix_obj.get("api_symbol", VIX_SYMBOL),
    }
    payload = json.dumps(out)
    r.set(VIX_KEY_LATEST, payload)
    try:
        r.zadd(VIX_KEY_TRAIL, {payload: ts_sec})
        r.zremrangebyscore(VIX_KEY_TRAIL, 0, ts_sec - VIX_TRAIL_TTL)
    except Exception:
        pass
    if USE_PUBSUB:
        try:
            r.publish(VIX_CHANNEL, json.dumps({"type": "vix", "ts": ts_iso, "key": VIX_KEY_LATEST}))
        except Exception:
            pass
    print(f"📈 VIX={out['value']:.2f} ts={out['ts']} -> {VIX_KEY_LATEST}")

# ==========================
# Mappers / diffs
# ==========================

def minimal_contract(c: dict) -> dict:
    d = c.get("details") or {}
    out = {
        "ticker": d.get("ticker"),
        "k": d.get("strike_price"),
        "cp": d.get("contract_type"),
    }
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


def comp_sig(contract: dict) -> str:
    q = contract.get("last_quote") or {}
    g = contract.get("greeks") or {}
    s = f"{q.get('bid')}:{q.get('ask')}:{g.get('delta')}:{g.get('gamma')}:{g.get('theta')}:{g.get('vega')}"
    return hashlib.blake2b(s.encode(), digest_size=12).hexdigest()


def compute_diff(
    new_chain: List[dict],
    prev_map: Dict[str, dict],
    prev_hash: Dict[str, str],
) -> dict:
    new_map = {
        (c.get("details", {}) or {}).get("ticker"): c
        for c in new_chain
        if (c.get("details") or {}).get("ticker")
    }
    new_set = set(new_map.keys())
    new_hash = {t: comp_sig(new_map[t]) for t in new_set}
    if not isinstance(prev_map, dict):
        prev_map = {}
    if not isinstance(prev_hash, dict):
        prev_hash = {}
    prev_set = set(prev_map.keys())
    added = list(new_set - prev_set)
    removed = list(prev_set - new_set)
    changed = [t for t in (new_set & prev_set) if new_hash[t] != prev_hash.get(t)]
    updates = [minimal_contract(new_map[t]) for t in changed]
    return {
        "added": added,
        "removed": removed,
        "updates": updates,
        "new_map": new_map,
        "new_hash": new_hash,
        "delta_count": len(added) + len(removed) + len(updates),
    }

# ==========================
# Persistence (+ Pub/Sub)
# ==========================

def _build_payloads(chain: List[dict]) -> Tuple[List[dict], List[dict]]:
    raw_payload = [full_contract(c) for c in chain]
    primary = raw_payload if SNAPSHOT_MODE == "full" else [minimal_contract(c) for c in chain]
    return primary, raw_payload


def _store_to_namespace(
    Kns,
    ts_iso: str,
    exp_date: str,
    spot: float,
    spot_src: str,
    primary_payload: List[dict],
    raw_payload: List[dict],
    diff_obj: Optional[dict],
    publish: bool,
    pub_full_channel: Optional[str] = None,
    pub_diff_channel: Optional[str] = None,
):
    r = _redis()
    ts_epoch = now_epoch()

    total_oi = 0
    total_vol = 0
    for c in raw_payload:
        oi = c.get("open_interest")
        vol = c.get("volume")
        if isinstance(oi, (int, float)):
            total_oi += oi
        if isinstance(vol, (int, float)):
            total_vol += vol

    base = {
        "symbol":     SYMBOL,
        "api_symbol": API_SYMBOL,
        "ts":         ts_iso,
        "expiration": exp_date,
        "spot":       spot,
        "spot_source": spot_src,
        "total_open_interest": total_oi,
        "total_volume":        total_vol,
    }
    if TAG_BACKFILL:
        try:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            base["is_backfill"]  = exp_date < today
            base["is_lookahead"] = exp_date > today
        except Exception:
            base["is_backfill"]  = False
            base["is_lookahead"] = False

    primary_obj = dict(base, **{"count": len(primary_payload), "contracts": primary_payload, "mode": SNAPSHOT_MODE})
    raw_obj     = dict(base, **{"count": len(raw_payload),   "contracts": raw_payload})

    primary_key = Kns.snapshot_key(ts_iso)
    raw_key     = Kns.snapshot_raw_key(ts_iso)

    pipe = r.pipeline(transaction=True)
    # snapshot payloads: keep alive for SNAPSHOT_TTL_SECONDS
    pipe.set(primary_key, json.dumps(primary_obj))
    pipe.expire(primary_key, SNAPSHOT_TTL_SECONDS)
    pipe.set(raw_key, json.dumps(raw_obj))
    pipe.expire(raw_key, SNAPSHOT_TTL_SECONDS)

    # pointers + trails
    pipe.set(Kns.latest_full, primary_key)
    pipe.zadd(Kns.trail_full, {primary_key: ts_epoch})
    pipe.set(Kns.latest_full_raw, raw_key)
    pipe.zadd(Kns.trail_full_raw, {raw_key: ts_epoch})

    # trim trails to TRAIL_TTL_SECONDS horizon if configured
    if TRAIL_TTL_SECONDS > 0:
        cutoff = ts_epoch - TRAIL_TTL_SECONDS
        pipe.zremrangebyscore(Kns.trail_full, 0, cutoff)
        pipe.zremrangebyscore(Kns.trail_full_raw, 0, cutoff)

    if diff_obj is not None:
        diff_key = Kns.diff_key(ts_iso)
        pipe.set(diff_key, json.dumps(diff_obj))
        pipe.expire(diff_key, SNAPSHOT_TTL_SECONDS)
        pipe.set(getattr(Kns, "latest_diff"), diff_key)
        pipe.zadd(getattr(Kns, "trail_diff"), {diff_key: ts_epoch})
        if TRAIL_TTL_SECONDS > 0:
            cutoff = ts_epoch - TRAIL_TTL_SECONDS
            pipe.zremrangebyscore(getattr(Kns, "trail_diff"), 0, cutoff)

    pipe.execute()

    if publish and USE_PUBSUB:
        try:
            ch_full = pub_full_channel or FULL_CHANNEL
            r.publish(
                ch_full,
                json.dumps(
                    {
                        "type": "full",
                        "symbol": SYMBOL,
                        "api_symbol": API_SYMBOL,
                        "ts": ts_iso,
                        "key": primary_key,
                        "count": len(primary_payload),
                        "total_volume": total_vol,
                        "total_oi": total_oi,
                        "mode": SNAPSHOT_MODE,
                    }
                ),
            )
            if diff_obj is not None:
                ch_diff = pub_diff_channel or DIFF_CHANNEL
                r.publish(
                    ch_diff,
                    json.dumps(
                        {
                            "type": "diff",
                            "symbol": SYMBOL,
                            "api_symbol": API_SYMBOL,
                            "ts": ts_iso,
                            "key": Kns.diff_key(ts_iso),
                            "diff_count": diff_obj.get("diff_count", 0),
                            "added": len(diff_obj.get("added", [])),
                            "removed": len(diff_obj.get("removed", [])),
                            "updated": len(diff_obj.get("updates", [])),
                        }
                    ),
                )
        except Exception as e:
            print(f"⚠️  Pub/Sub publish error: {e}")


def _update_dte_alias_pointers(exp_ymd: str, dte: int):
    if not USE_DTE_ALIASES:
        return
    r = _redis()
    alias = dte_alias_keys(SYMBOL, dte)
    kexp = ExpKeys(SYMBOL, exp_ymd)
    pipe = r.pipeline(transaction=True)
    lf = r.get(kexp.latest_full)
    lfr = r.get(kexp.latest_full_raw)
    ldf = r.get(kexp.latest_diff) if r.exists(kexp.latest_diff) else None
    if lf:
        pipe.set(alias.latest_full, lf)
    if lfr:
        pipe.set(alias.latest_full_raw, lfr)
    if ldf:
        pipe.set(alias.latest_diff, ldf)
    pipe.execute()

# ==========================
# Loop
# ==========================

_running = True


def _handle_stop(sig, frame):
    global _running
    _running = False
    print(f"🛑 Received signal {sig}, stopping worker…")


signal.signal(signal.SIGTERM, _handle_stop)
signal.signal(signal.SIGINT, _handle_stop)


def _choose_sleep(delta_count: int) -> float:
    if delta_count >= HOT_DELTA:
        return SLEEP_MIN_S
    if delta_count <= QUIET_DELTA:
        return SLEEP_MAX_S
    span = max(HOT_DELTA - QUIET_DELTA, 1)
    frac = (delta_count - QUIET_DELTA) / span
    return max(SLEEP_MIN_S, min(SLEEP_MAX_S, SLEEP_MAX_S - (SLEEP_MAX_S - SLEEP_MIN_S) * frac))


def _diagnose_chain(rows: List[dict], label: str):
    total = len(rows)
    with_greeks = sum(1 for c in rows if (c.get("greeks") or {}).get("gamma") is not None)
    with_any_iv = sum(
        1
        for c in rows
        if (c.get("greeks") or {}).get("iv") is not None
           or c.get("iv") is not None
           or c.get("implied_volatility") is not None
    )
    with_q = sum(
        1
        for c in rows
        if (c.get("last_quote") or {}).get("bid") is not None
           or (c.get("last_quote") or {}).get("ask") is not None
    )
    with_oi = sum(1 for c in rows if isinstance(c.get("open_interest"), (int, float)))
    print(
        f"  [{label}] contracts={total}  withGamma={with_greeks}  "
        f"withAnyIV={with_any_iv}  withBid/Ask={with_q}  withOI={with_oi}"
    )
    if with_greeks == 0:
        print("  ⚠️  No greeks in snapshot — check include_greeks=true and API_SYMBOL (I:SPX).")


def run_once() -> int:
    """One sweep across DTE_LIST. Returns total delta_count across expiries."""
    if K_legacy is None or K_multi is None:
        # Minimal safeguard: if orchestrator forgot, assume env-driven config.
        configure_from_env()

    r = _redis()  # ensure connection early
    expiries = _expiries_for(DTE_LIST)
    t0 = datetime.now(timezone.utc)
    ts = t0.isoformat(timespec="seconds")
    print(f"[{ts}] Sweep DTE {DTE_LIST} (Underlying={SYMBOL}, API={API_SYMBOL})")

    total_delta = 0

    # Massive spot once per sweep
    spot_val: Optional[float] = None
    spot_src: str = "massive_snapshot"
    index_symbol = API_SYMBOL  # Massive expects index-style symbol, same as Polygon
    try:
        # MASSIVE_API_KEY may be empty; get_spot will then use its own module API_KEY.
        spot_val = massive_spot.get_spot(index_symbol, api_key=MASSIVE_API_KEY or None)
        print(f"  📍 Massive spot: {index_symbol} = {spot_val}")
    except Exception as e:
        print(f"  ⚠️ Massive spot fetch failed for {index_symbol}: {e}")
        spot_src = "none"

    # combined multi-DTE buffers
    combined_primary: List[dict] = []
    combined_raw: List[dict] = []
    combined_expiries: List[str] = []
    combined_spot: Optional[float] = spot_val
    combined_spot_source: str = spot_src or "massive_snapshot"
    combined_dte_by_exp: Dict[str, int] = {}

    state_key = f"{SYMBOL}:worker:prev_state"
    try:
        prev_state = json.loads(r.get(state_key) or "{}")
    except Exception:
        prev_state = {}
    if not isinstance(prev_state, dict):
        prev_state = {}
    else:
        for _exp, st in list(prev_state.items()):
            if not isinstance(st, dict):
                prev_state[_exp] = {}
                continue
            if not isinstance(st.get("prev_map"), dict):
                st["prev_map"] = {}
            if not isinstance(st.get("prev_hash"), dict):
                st["prev_hash"] = {}

    for idx, exp in enumerate(expiries):
        try:
            rows = _paginate_snapshot_expiration(API_SYMBOL, exp)
            _diagnose_chain(rows, f"EXP {exp}")

            # If Polygon returns nothing (weekends/holidays), *do not* overwrite anything.
            if not rows:
                print(
                    f"  DTE slot {idx} | {exp} | 0 contracts from Polygon → "
                    f"skipping store + aliases (keep previous pointers)."
                )
                continue

            local_spot = float(spot_val) if isinstance(spot_val, (int, float)) else float("nan")
            local_src  = spot_src

            # diff
            prev_map  = prev_state.get(exp, {}).get("prev_map", {})
            prev_hash = prev_state.get(exp, {}).get("prev_hash", {})
            primary, raw = _build_payloads(rows)
            diff = compute_diff(
                rows,
                prev_map if isinstance(prev_map, dict) else {},
                prev_hash if isinstance(prev_hash, dict) else {},
            )
            prev_state.setdefault(exp, {})["prev_map"]  = diff["new_map"]
            prev_state.setdefault(exp, {})["prev_hash"] = diff["new_hash"]
            delta = diff["delta_count"]
            total_delta += delta

            # integer DTE
            dte_num = (datetime.fromisoformat(exp).date() - t0.date()).days
            combined_dte_by_exp[exp] = dte_num

            # tag for combined view
            tagged_primary: List[dict] = []
            for c in primary:
                cc = dict(c)
                cc.setdefault("exp", exp)
                cc.setdefault("dte", dte_num)
                tagged_primary.append(cc)
            tagged_raw: List[dict] = []
            for c in raw:
                cc = dict(c)
                det = cc.get("details")
                if isinstance(det, dict) and not det.get("expiration_date"):
                    det["expiration_date"] = exp
                cc.setdefault("dte", dte_num)
                tagged_raw.append(cc)

            combined_primary.extend(tagged_primary)
            combined_raw.extend(tagged_raw)
            combined_expiries.append(exp)

            # per-expiry namespace
            Kexp = ExpKeys(SYMBOL, exp)

            # Only do diff for 0DTE unless DIFF_FOR_ALL=1
            if idx != 0 and not DIFF_FOR_ALL:
                diff_obj = None
            else:
                diff_obj = {
                    "symbol": SYMBOL,
                    "api_symbol": API_SYMBOL,
                    "ts": ts,
                    "expiration": exp,
                    "spot": local_spot if isinstance(local_spot, (int, float)) else None,
                    "diff_count": delta,
                    "added": diff["added"],
                    "removed": diff["removed"],
                    "updates": diff["updates"],
                }

            _store_to_namespace(
                Kexp,
                ts,
                exp,
                local_spot,
                local_src,
                primary,
                raw,
                diff_obj,
                publish=True if USE_EXP_PUBSUB else False,
                pub_full_channel=f"{SYMBOL}:EXP:{exp}:chan:full",
                pub_diff_channel=f"{SYMBOL}:EXP:{exp}:chan:diff",
            )

            # DTE alias pointer (only for expiries with real data)
            if USE_DTE_ALIASES:
                _update_dte_alias_pointers(exp, idx)

            # legacy 0DTE keys for the first expiry only
            if idx == 0 and K_legacy is not None:
                _store_to_namespace(
                    K_legacy,
                    ts,
                    exp,
                    local_spot,
                    local_src,
                    primary,
                    raw,
                    diff_obj,
                    publish=True,
                )

            calls = sum(1 for c in rows if (c.get("details") or {}).get("contract_type") == "call")
            puts  = sum(1 for c in rows if (c.get("details") or {}).get("contract_type") == "put")
            strikes = [
                (c.get("details") or {}).get("strike_price")
                for c in rows
                if isinstance((c.get("details") or {}).get("strike_price"), (int, float))
            ]
            kmin = min(strikes) if strikes else float("nan")
            kmax = max(strikes) if strikes else float("nan")
            print(
                f"  DTE {dte_num:>2} | {exp} | contracts={len(rows):4d} "
                f"calls={calls:4d} puts={puts:4d} strike_range=({kmin}, {kmax}) Δ={delta}"
            )

        except Exception as e:
            print(f"  [!] {exp} fetch/store error: {e}")

    # combined multi-DTE snapshot
    try:
        if combined_primary and K_multi is not None:
            multi_ts_key        = f"{SYMBOL}:multi_dte:chain:{ts}"
            multi_ts_raw_key    = f"{SYMBOL}:multi_dte:chain_raw:{ts}"
            latest_full_ptr     = f"{SYMBOL}:multi_dte:latest_full"
            latest_full_raw_ptr = f"{SYMBOL}:multi_dte:latest_full_raw"

            expirations_dte = [
                {"expiration": exp, "dte": combined_dte_by_exp.get(exp)}
                for exp in combined_expiries
            ]

            base = {
                "symbol": SYMBOL,
                "api_symbol": API_SYMBOL,
                "ts": ts,
                "expirations": combined_expiries,
                "expirations_dte": expirations_dte,
                "spot": combined_spot if isinstance(combined_spot, (int, float)) else float("nan"),
                "spot_source": combined_spot_source,
                "total_open_interest": 0,
                "total_volume": 0,
            }

            primary_obj = dict(
                base,
                **{
                    "count": len(combined_primary),
                    "contracts": combined_primary,
                    "mode": SNAPSHOT_MODE,
                },
            )
            raw_obj = dict(
                base,
                **{
                    "count": len(combined_raw),
                    "contracts": combined_raw,
                },
            )

            pipe = r.pipeline(transaction=True)
            pipe.set(multi_ts_key, json.dumps(primary_obj))
            pipe.expire(multi_ts_key, SNAPSHOT_TTL_SECONDS)
            pipe.set(multi_ts_raw_key, json.dumps(raw_obj))
            pipe.expire(multi_ts_raw_key, SNAPSHOT_TTL_SECONDS)
            pipe.set(latest_full_ptr,     multi_ts_key)
            pipe.set(latest_full_raw_ptr, multi_ts_raw_key)
            pipe.zadd(K_multi.trail_full,     {multi_ts_key: now_epoch()})
            pipe.zadd(K_multi.trail_full_raw, {multi_ts_raw_key: now_epoch()})
            if TRAIL_TTL_SECONDS > 0:
                cutoff = now_epoch() - TRAIL_TTL_SECONDS
                pipe.zremrangebyscore(K_multi.trail_full,     0, cutoff)
                pipe.zremrangebyscore(K_multi.trail_full_raw, 0, cutoff)
            pipe.execute()

            print(
                f"  🔗 multi-DTE combined snapshot: expiries={combined_expiries} "
                f"contracts={len(combined_primary)} -> {latest_full_ptr} -> {multi_ts_key}"
            )
        else:
            print("  ⚠️ No combined_primary contracts; multi-DTE snapshot not written this sweep.")
    except Exception as e:
        print(f"  [!] multi-DTE snapshot store error: {e}")

    # ------------------------------------------------------------------
    # Fallback: if this is the first run after FLUSHALL (no legacy 0DTE),
    # seed SPX:latest_full(_raw) so the UI never goes completely blank.
    # ------------------------------------------------------------------
    try:
        r = _redis()
        if K_legacy is not None:
            has_legacy_raw = r.exists(K_legacy.latest_full_raw)
        else:
            has_legacy_raw = False

        if not has_legacy_raw:
            # Prefer a real combined multi-DTE snapshot if it exists
            lfr_multi = r.get(f"{SYMBOL}:multi_dte:latest_full_raw")
            lf_multi  = r.get(f"{SYMBOL}:multi_dte:latest_full")

            if lfr_multi and K_legacy is not None:
                r.set(K_legacy.latest_full_raw, lfr_multi)
                if lf_multi:
                    r.set(K_legacy.latest_full, lf_multi)
                else:
                    # fall back to raw pointer if minimal pointer missing
                    r.set(K_legacy.latest_full, lfr_multi)

                print(
                    f"  ⚠️ No legacy 0DTE pointer found; seeded "
                    f"{K_legacy.latest_full_raw} from multi-DTE."
                )
    except Exception as e:
        print(f"  [!] error while seeding legacy 0DTE pointer: {e}")

    # persist prev_state snapshot
    try:
        _redis().set(state_key, json.dumps(prev_state))
    except Exception:
        pass

    # VIX once per sweep via Massive
    try:
        v = fetch_vix_from_massive()
        if v:
            store_vix_snapshot(v)
    except Exception:
        pass

    print(f"  ✓ sweep done • Δ_total={total_delta}")
    return total_delta


def run_loop() -> None:
    last_publish_at: float = 0.0
    if K_legacy is None or K_multi is None:
        configure_from_env()
    while _running:
        try:
            delta = run_once()
            now = time.time()
            force_due = (FORCE_PUBLISH_INTERVAL_S > 0) and (
                (now - last_publish_at) >= FORCE_PUBLISH_INTERVAL_S
            )
            if delta > 0 or force_due:
                last_publish_at = now
            time.sleep(_choose_sleep(delta))
        except Exception as e:
            print(f"⚠️  {e}")
            time.sleep(0.5)

# ==========================
# CLI
# ==========================

def main():
    import argparse

    p = argparse.ArgumentParser(description="DTE Feed Worker (Polygon → Redis)")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("start", help="run continuous loop")
    sub.add_parser("once", help="run single sweep and exit")
    args = p.parse_args()

    # CLI path still uses env, but no secrets are baked in.
    configure_from_env()

    if args.cmd == "once":
        run_once()
    else:
        print(
            f"Starting DTE feed worker. SYMBOL={SYMBOL} API_SYMBOL={API_SYMBOL} "
            f"DTE_LIST={DTE_LIST}"
        )
        print(
            f"Redis {REDIS_HOST}:{REDIS_PORT}/{REDIS_DB} | "
            f"PubSub={USE_PUBSUB} | SnapshotMode={SNAPSHOT_MODE}"
        )
        run_loop()


if __name__ == "__main__":
    main()