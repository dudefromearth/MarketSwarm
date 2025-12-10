#!/usr/bin/env python3
# services/mmaker/strategies/vertical.py

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from redis.asyncio import Redis


@dataclass
class VerticalTile:
    strategy: str
    underlying: str
    exp: str            # "YYYY-MM-DD"
    lower_strike: float
    upper_strike: float
    direction: str      # "bull_call", "bear_put", etc.
    legs: List[Dict[str, Any]]
    debit_credit: Optional[float]  # Positive debit, negative credit
    max_profit: Optional[float]
    max_loss: Optional[float]
    r2r: Optional[float]
    spot: float


def _extract_mid_from_contract(raw: Dict[str, Any]) -> Optional[float]:
    # Reuse from butterfly.py
    q = raw.get("last_quote") or raw.get("quote") or {}
    bid = q.get("bid") or q.get("bid_price")
    ask = q.get("ask") or q.get("ask_price")
    try:
        if bid is not None and ask is not None:
            return 0.5 * (float(bid) + float(ask))
    except (TypeError, ValueError):
        pass
    t = raw.get("last_trade") or raw.get("trade") or {}
    last = t.get("price") or t.get("p")
    try:
        if last is not None:
            return float(last)
    except (TypeError, ValueError):
        pass
    return None


def _parse_contract(raw: Dict[str, Any]) -> Optional[Tuple[str, float, str, float]]:
    """Return (right, strike, exp, mid) or None."""
    details = raw.get("details") or {}
    right = details.get("type") or details.get("option_type") or details.get("right")
    sym = details.get("symbol") or raw.get("symbol") or ""
    if "C" in sym and not right:
        right = "C"
    elif "P" in sym and not right:
        right = "P"
    if not right or right.upper() not in ("C", "P"):
        return None
    right = right.upper()
    strike = details.get("strike_price")
    exp = details.get("expiration_date")
    if strike is None or not exp:
        return None
    try:
        strike_f = float(strike)
    except (TypeError, ValueError):
        return None
    mid = _extract_mid_from_contract(raw)
    return right, strike_f, exp, mid


def _build_option_surface(contracts: List[Dict[str, Any]]) -> Dict[Tuple[str, str, float], float]:
    """Key: (right, exp, strike) -> mid price."""
    surface = {}
    for raw in contracts:
        parsed = _parse_contract(raw)
        if parsed is None or parsed[3] is None:
            continue
        right, strike, exp, mid = parsed
        key = (right, exp, strike)
        surface[key] = mid
    return surface


def _build_strike_list(surface: Dict[Tuple[str, str, float], float], right: str, exp: str) -> List[float]:
    strikes = sorted({strike for (r, e, strike) in surface if r == right and e == exp})
    return strikes


def _find_near_strikes(strikes: List[float], spot: float, step: float, num_legs: int = 2) -> List[float]:
    """Find closest strikes to spot for vertical (e.g., 2 legs)."""
    atm = round(spot / step) * step
    candidates = sorted(strikes, key=lambda k: abs(k - spot))[:num_legs * 2]  # Buffer
    return sorted(candidates[:num_legs])  # Simplest: lowest/highest near ATM


def _make_vertical_legs(direction: str, lower_k: float, upper_k: float, exp: str, surface: Dict[Tuple[str, str, float], float]) -> Optional[Tuple[List[Dict[str, Any]], float]]:
    """Build 2-leg vertical, compute debit/credit."""
    if lower_k >= upper_k:
        return None
    if direction == "bull_call":
        right = "C"
        # Long lower, short upper
        q_lower = surface.get((right, exp, lower_k))
        q_upper = surface.get((right, exp, upper_k))
    elif direction == "bear_put":
        right = "P"
        q_lower = surface.get((right, exp, lower_k))  # Long lower put
        q_upper = surface.get((right, exp, upper_k))  # Short upper put
    else:
        return None

    if q_lower is None or q_upper is None:
        return None

    m_lower = float(q_lower)
    m_upper = float(q_upper)

    # Debit for calls/puts: long - short
    debit_credit = m_lower - m_upper  # Positive debit, negative credit

    legs = [
        {"side": "long", "qty": 1, "right": right, "strike": lower_k, "exp": exp, "mid": m_lower},
        {"side": "short", "qty": 1, "right": right, "strike": upper_k, "exp": exp, "mid": m_upper},
    ]

    return legs, debit_credit


async def build_vertical_grid_from_chain(
    redis_url: str,
    underlying: str,
    exp_iso: str,
    spot_key: Optional[str] = None,
    chain_latest_key: Optional[str] = None,
    strike_step: float = 5.0,
    min_width: float = 5.0,
    max_width: float = 50.0,
    width_step: float = 5.0,
) -> None:
    """Build vertical grid, write to mm:{U}:vertical:{exp}:grid."""
    r = Redis.from_url(redis_url, decode_responses=True)

    # Load spot
    spot_key = spot_key or f"massive:model:spot:{underlying}"
    raw_spot = await r.get(spot_key)
    if not raw_spot:
        raise RuntimeError(f"Spot key missing: {spot_key}")
    spot_data = json.loads(raw_spot)
    spot_val = float(spot_data.get("value"))

    # Load chain
    latest_key = chain_latest_key or f"CHAIN:{underlying}:EXP:{exp_iso}:latest"
    snap_pointer = await r.get(latest_key)
    if not snap_pointer:
        raise RuntimeError(f"Chain latest pointer missing: {latest_key}")
    raw_snap = await r.get(snap_pointer)
    if not raw_snap:
        raise RuntimeError(f"Chain snapshot missing: {snap_pointer}")
    snap = json.loads(raw_snap)
    contracts = snap.get("contracts", [])
    if not contracts:
        raise RuntimeError(f"No contracts in chain: {snap_pointer}")

    # Build surface
    surface = _build_option_surface(contracts)
    if not surface:
        raise RuntimeError("No usable options")

    strikes_call = _build_strike_list(surface, "C", exp_iso)
    strikes_put = _build_strike_list(surface, "P", exp_iso)
    if not strikes_call or not strikes_put:
        raise RuntimeError("No strikes for calls or puts")

    # Build tiles
    widths = [w for w in range(int(min_width), int(max_width) + 1, int(width_step))]
    all_tiles = []

    # Bull calls (above spot)
    for lower in strikes_call:
        if lower < spot_val:  # Skip OTM for bull
            continue
        for w in widths:
            upper = lower + w
            if upper not in strikes_call:
                continue
            legs_debit = _make_vertical_legs("bull_call", lower, upper, exp_iso, surface)
            if legs_debit is None:
                continue
            legs, dc = legs_debit
            max_profit = w - abs(dc) if dc > 0 else w
            max_loss = abs(dc)
            r2r = max_profit / max_loss if max_loss > 0 else None
            tile = VerticalTile(
                strategy="vertical",
                underlying=underlying,
                exp=exp_iso,
                lower_strike=lower,
                upper_strike=upper,
                direction="bull_call",
                legs=legs,
                debit_credit=dc,
                max_profit=max_profit,
                max_loss=max_loss,
                r2r=r2r,
                spot=spot_val,
            )
            all_tiles.append({
                "strategy": tile.strategy,
                "underlying": tile.underlying,
                "exp": tile.exp,
                "tile_id": f"{tile.direction}_K{lower}-{upper}",
                "lower_strike": tile.lower_strike,
                "upper_strike": tile.upper_strike,
                "direction": tile.direction,
                "legs": tile.legs,
                "debit_credit": tile.debit_credit,
                "max_profit": tile.max_profit,
                "max_loss": tile.max_loss,
                "r2r": tile.r2r,
                "spot": tile.spot,
            })

    # Bear puts (below spot) - similar logic
    for upper in strikes_put:
        if upper > spot_val:  # Skip OTM for bear
            continue
        for w in widths:
            lower = upper - w
            if lower not in strikes_put:
                continue
            legs_dc = _make_vertical_legs("bear_put", lower, upper, exp_iso, surface)
            if legs_dc is None:
                continue
            legs, dc = legs_dc
            max_profit = w + dc if dc < 0 else w  # Credit spreads
            max_loss = abs(dc)
            r2r = max_profit / max_loss if max_loss > 0 else None
            tile = VerticalTile(
                strategy="vertical",
                underlying=underlying,
                exp=exp_iso,
                lower_strike=lower,
                upper_strike=upper,
                direction="bear_put",
                legs=legs,
                debit_credit=dc,
                max_profit=max_profit,
                max_loss=max_loss,
                r2r=r2r,
                spot=spot_val,
            )
            all_tiles.append({
                "strategy": tile.strategy,
                "underlying": tile.underlying,
                "exp": tile.exp,
                "tile_id": f"{tile.direction}_K{lower}-{upper}",
                "lower_strike": tile.lower_strike,
                "upper_strike": tile.upper_strike,
                "direction": tile.direction,
                "legs": tile.legs,
                "debit_credit": tile.debit_credit,
                "max_profit": tile.max_profit,
                "max_loss": tile.max_loss,
                "r2r": tile.r2r,
                "spot": tile.spot,
            })

    # Serialize grid
    grid = {
        "strategy": "vertical",
        "underlying": underlying,
        "exp": exp_iso,
        "spot": spot_val,
        "widths": widths,
        "strike_step": strike_step,
        "tile_count": len(all_tiles),
        "tiles": all_tiles,
    }

    key = f"mm:{underlying}:vertical:{exp_iso}:grid"
    await r.set(key, json.dumps(grid))

    await r.aclose()


if __name__ == "__main__":
    import asyncio
    import sys

    if len(sys.argv) != 3:
        print("Usage: python -m mmaker.strategies.vertical SPX 2025-12-09")
        sys.exit(1)

    underlying = sys.argv[1]
    exp_iso = sys.argv[2]

    redis_url = os.getenv("MARKET_REDIS_URL", "redis://127.0.0.1:6380")

    async def _run():
        await build_vertical_grid_from_chain(
            redis_url=redis_url,
            underlying=underlying,
            exp_iso=exp_iso,
            strike_step=float(os.getenv("MASSIVE_WS_STRIKE_STEP", "5")),
        )
        print(f"✅ Built vertical grid for {underlying} {exp_iso}")

    asyncio.run(_run())