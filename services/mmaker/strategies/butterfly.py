#!/usr/bin/env python3
# services/mmaker/strategies/butterfly.py

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from redis.asyncio import Redis

# ----------------------------------------------------------------------
# Data structures
# ----------------------------------------------------------------------


@dataclass
class OptionQuote:
    right: str          # "C" or "P"
    strike: float
    exp: str            # "YYYY-MM-DD"
    mid: Optional[float]


@dataclass
class ButterflyTile:
    strategy: str
    underlying: str
    exp: str            # "YYYY-MM-DD"
    center_strike: float
    width: float
    direction: str      # "call" or "put"
    legs: List[Dict[str, Any]]
    debit: Optional[float]
    max_profit: Optional[float]
    max_loss: Optional[float]
    r2r: Optional[float]
    convexity_score: Optional[float]
    spot: float


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _round_to_step(x: float, step: float) -> float:
    return round(x / step) * step


def _extract_mid_from_contract(raw: Dict[str, Any]) -> Optional[float]:
    """
    Heuristic mid-price extractor from a Massive contract dict.

    You *will* want to align this with the actual schema of contracts
    in CHAIN snapshots (e.g., last_quote.bid/ask, last_trade.price, etc.).
    """
    # Try last_quote
    q = raw.get("last_quote") or raw.get("quote") or {}
    bid = q.get("bid") or q.get("bid_price")
    ask = q.get("ask") or q.get("ask_price")
    try:
        if bid is not None and ask is not None:
            return 0.5 * (float(bid) + float(ask))
    except (TypeError, ValueError):
        pass

    # Fallback: last_trade
    t = raw.get("last_trade") or raw.get("trade") or {}
    last = t.get("price") or t.get("p")
    try:
        if last is not None:
            return float(last)
    except (TypeError, ValueError):
        pass

    # No usable price
    return None


def _parse_contract(raw: Dict[str, Any]) -> Optional[OptionQuote]:
    """
    Convert a Massive contract dict from CHAIN snapshot into OptionQuote.
    """
    details = raw.get("details") or {}

    right = details.get("type") or details.get("option_type") or details.get("right")
    if not right:
        # Try deriving from symbol if all else fails
        sym = details.get("symbol") or raw.get("symbol") or ""
        if "C" in sym:
            right = "C"
        elif "P" in sym:
            right = "P"

    if not right:
        return None

    right = right.upper()
    if right not in ("C", "P"):
        return None

    strike = details.get("strike_price")
    exp = details.get("expiration_date")  # expected "YYYY-MM-DD"
    if strike is None or not exp:
        return None

    try:
        strike_f = float(strike)
    except (TypeError, ValueError):
        return None

    mid = _extract_mid_from_contract(raw)

    return OptionQuote(
        right=right,
        strike=strike_f,
        exp=exp,
        mid=mid,
    )


def _build_option_surface(
    contracts: List[Dict[str, Any]],
) -> Dict[Tuple[str, float], OptionQuote]:
    """
    Build a dict keyed by (right, strike) for fast lookup.

    key = ( "C" or "P", strike_float )
    """
    surface: Dict[Tuple[str, float], OptionQuote] = {}
    for raw in contracts:
        oq = _parse_contract(raw)
        if oq is None:
            continue
        key = (oq.right, oq.strike)
        surface[key] = oq
    return surface


def _build_strike_list(surface: Dict[Tuple[str, float], OptionQuote]) -> List[float]:
    strikes = sorted({strike for (_, strike) in surface.keys()})
    return strikes


def _find_atm_strike(strikes: List[float], spot: float, step: float) -> float:
    """
    ATM = strike closest to rounded spot.
    """
    approx = _round_to_step(spot, step)
    best = min(strikes, key=lambda k: abs(k - approx))
    return best


def _make_fly_legs(
    direction: str,
    center: float,
    width: float,
    exp: str,
    surface: Dict[Tuple[str, float], OptionQuote],
) -> Optional[Tuple[List[Dict[str, Any]], float]]:
    """
    Build legs and debit for a single symmetric 1–2–1 fly.

    direction: "call" or "put"
    center:   K
    width:    W
    """
    W = width
    K = center

    if direction == "call":
        right = "C"
        k1, k2, k3 = K - W, K, K + W
    else:
        right = "P"
        k1, k2, k3 = K + W, K, K - W

    # Look up mid prices
    q1 = surface.get((right, k1))
    q2 = surface.get((right, k2))
    q3 = surface.get((right, k3))

    if not q1 or not q2 or not q3:
        return None

    if q1.mid is None or q2.mid is None or q3.mid is None:
        return None

    m1 = float(q1.mid)
    m2 = float(q2.mid)
    m3 = float(q3.mid)

    if direction == "call":
        debit = m1 - 2.0 * m2 + m3
    else:
        # For puts we wrote long(K+W), short 2 @ K, long(K-W)
        debit = m1 - 2.0 * m2 + m3

    legs = [
        {
            "side": "long",
            "qty": 1,
            "right": right,
            "strike": k1,
            "exp": exp,
            "mid": m1,
        },
        {
            "side": "short",
            "qty": 2,
            "right": right,
            "strike": k2,
            "exp": exp,
            "mid": m2,
        },
        {
            "side": "long",
            "qty": 1,
            "right": right,
            "strike": k3,
            "exp": exp,
            "mid": m3,
        },
    ]

    return legs, debit


# ----------------------------------------------------------------------
# Butterfly grid builder
# ----------------------------------------------------------------------


async def build_butterfly_grid_from_chain(
    redis_url: str,
    underlying: str,
    exp_iso: str,     # "YYYY-MM-DD"
    spot_key: Optional[str] = None,
    chain_latest_key: Optional[str] = None,
    strike_step: float = 5.0,
    min_width: float = 10.0,
    max_width: float = 60.0,
    width_step: float = 5.0,
) -> None:
    """
    Read latest CHAIN snapshot + spot from Redis, build butterfly grid,
    and write it to mm:{U}:butterfly:{exp}:grid.

    - underlying: "SPX"
    - exp_iso:    "2025-12-09"
    """

    r = Redis.from_url(redis_url, decode_responses=True)

    # -------------------------
    # 1) Load spot
    # -------------------------
    spot_key = spot_key or f"massive:model:spot:{underlying}"
    raw_spot = await r.get(spot_key)
    if not raw_spot:
        raise RuntimeError(f"Spot key missing: {spot_key}")

    try:
        spot_data = json.loads(raw_spot)
        spot_val = float(spot_data.get("value"))
    except Exception as e:
        raise RuntimeError(f"Bad spot JSON at {spot_key}: {e}")

    # -------------------------
    # 2) Load chain snapshot
    # -------------------------
    latest_key = chain_latest_key or f"CHAIN:{underlying}:EXP:{exp_iso}:latest"
    snap_pointer = await r.get(latest_key)
    if not snap_pointer:
        raise RuntimeError(f"Chain latest pointer missing: {latest_key}")

    raw_snap = await r.get(snap_pointer)
    if not raw_snap:
        raise RuntimeError(f"Chain snapshot missing: {snap_pointer}")

    try:
        snap = json.loads(raw_snap)
    except Exception as e:
        raise RuntimeError(f"Bad chain snapshot JSON at {snap_pointer}: {e}")

    contracts = snap.get("contracts") or []
    if not isinstance(contracts, list) or not contracts:
        raise RuntimeError(f"No contracts in chain snapshot {snap_pointer}")

    # -------------------------
    # 3) Build option surface
    # -------------------------
    surface = _build_option_surface(contracts)
    if not surface:
        raise RuntimeError(f"No usable options in chain snapshot {snap_pointer}")

    strikes = _build_strike_list(surface)
    if not strikes:
        raise RuntimeError(f"No strikes discovered in surface {snap_pointer}")

    atm = _find_atm_strike(strikes, spot_val, strike_step)

    # -------------------------
    # 4) Build raw tiles (without convexity)
    # -------------------------
    widths = []
    w = min_width
    while w <= max_width + 1e-6:
        widths.append(w)
        w += width_step

    tiles_by_width: Dict[float, List[ButterflyTile]] = {W: [] for W in widths}

    for K in strikes:
        # Skip strikes where you obviously can't fit the full fly,
        # i.e. if you'd go beyond min/max strike when building K±W.
        for W in widths:
            min_strike = min(strikes)
            max_strike = max(strikes)

            if K - W < min_strike and K + W > max_strike:
                continue  # can't build either way

            # Direction: below ATM -> puts, above ATM -> calls, ATM -> calls
            if K < atm:
                direction = "put"
            else:
                direction = "call"

            legs_debit = _make_fly_legs(
                direction=direction,
                center=K,
                width=W,
                exp=exp_iso,
                surface=surface,
            )
            if legs_debit is None:
                continue

            legs, debit = legs_debit

            # Risk metrics
            if debit is None or debit <= 0:
                max_profit = None
                max_loss = None
                r2r = None
            else:
                max_profit = W - debit
                max_loss = debit
                r2r = max_profit / max_loss if max_loss > 0 else None

            tile = ButterflyTile(
                strategy="butterfly",
                underlying=underlying,
                exp=exp_iso,
                center_strike=K,
                width=W,
                direction=direction,
                legs=legs,
                debit=debit,
                max_profit=max_profit,
                max_loss=max_loss,
                r2r=r2r,
                convexity_score=None,  # to be filled in later
                spot=spot_val,
            )
            tiles_by_width[W].append(tile)

    # -------------------------
    # 5) Compute convexity per width
    #    convexity(K) ~ debit(K+ΔK) - 2*debit(K) + debit(K-ΔK)
    # -------------------------
    for W, tiles in tiles_by_width.items():
        if len(tiles) < 3:
            continue

        # Sort by center_strike
        tiles.sort(key=lambda t: t.center_strike)

        # Map center_strike -> index
        # Then compute second finite difference across strikes.
        debits = [t.debit for t in tiles]
        strikes_w = [t.center_strike for t in tiles]

        # If all debits are None, skip
        if all(d is None for d in debits):
            continue

        # Compute raw convexities, skipping edges
        raw_conv: List[float] = [0.0] * len(tiles)
        for i in range(1, len(tiles) - 1):
            d_prev = debits[i - 1]
            d_curr = debits[i]
            d_next = debits[i + 1]
            if d_prev is None or d_curr is None or d_next is None:
                continue
            raw_conv[i] = (d_next - 2.0 * d_curr + d_prev)

        # Normalize into [-1, 1] based on max abs
        max_abs = max(abs(c) for c in raw_conv)
        if max_abs <= 0:
            continue

        for i, tile in enumerate(tiles):
            c = raw_conv[i]
            score = c / max_abs
            # Clamp just in case
            score = max(-1.0, min(1.0, score))
            tile.convexity_score = score

    # -------------------------
    # 6) Serialize + write grid to Redis
    # -------------------------
    all_tiles: List[Dict[str, Any]] = []
    for W, tiles in tiles_by_width.items():
        for t in tiles:
            all_tiles.append(
                {
                    "strategy": t.strategy,
                    "underlying": t.underlying,
                    "exp": t.exp,
                    "tile_id": f"K={t.center_strike}|W={t.width}",
                    "center_strike": t.center_strike,
                    "width": t.width,
                    "direction": t.direction,
                    "legs": t.legs,
                    "debit": t.debit,
                    "max_profit": t.max_profit,
                    "max_loss": t.max_loss,
                    "r2r": t.r2r,
                    "convexity_score": t.convexity_score,
                    "spot": t.spot,
                }
            )

    grid = {
        "strategy": "butterfly",
        "underlying": underlying,
        "exp": exp_iso,
        "spot": spot_val,
        "atm_strike": atm,
        "widths": widths,
        "strike_step": strike_step,
        "tile_count": len(all_tiles),
        "tiles": all_tiles,
    }

    key = f"mm:{underlying}:butterfly:{exp_iso}:grid"
    await r.set(key, json.dumps(grid))

    # Optionally: set TTL, but probably you want it “live” until replaced.
    # await r.expire(key, 300)

    await r.aclose()


# ----------------------------------------------------------------------
# CLI test harness (optional)
# ----------------------------------------------------------------------


if __name__ == "__main__":
    import asyncio
    import sys

    if len(sys.argv) != 3:
        print("Usage: python -m mmaker.strategies.butterfly SPX 2025-12-09")
        sys.exit(1)

    underlying = sys.argv[1]
    exp_iso = sys.argv[2]

    redis_url = os.getenv("MARKET_REDIS_URL", "redis://127.0.0.1:6380")

    async def _run():
        await build_butterfly_grid_from_chain(
            redis_url=redis_url,
            underlying=underlying,
            exp_iso=exp_iso,
            strike_step=float(os.getenv("MASSIVE_WS_STRIKE_STEP", "5")),
        )
        print(f"✅ Built butterfly grid for {underlying} {exp_iso}")

    asyncio.run(_run())