#!/usr/bin/env python3
"""
market_reader.py — Consume Massive models for Vexy AI

Reads from market-redis:
  - massive:model:spot:{symbol} — current spot prices
  - massive:gex:model:{symbol}:calls/puts — gamma exposure
  - massive:heatmap:model:{symbol}:latest — convexity heatmap
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

import redis


class MarketReader:
    """
    Reads market state from Massive models in market-redis.
    """

    SYMBOLS = ["I:SPX", "I:NDX", "I:VIX"]

    def __init__(self, r_market: redis.Redis, logger):
        self.r = r_market
        self.logger = logger

    def _safe_json(self, raw: Optional[str]) -> Optional[Dict]:
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def get_spot(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get current spot price for a symbol."""
        raw = self.r.get(f"massive:model:spot:{symbol}")
        return self._safe_json(raw)

    def get_gex(self, symbol: str) -> Dict[str, Any]:
        """Get GEX model for a symbol (calls and puts)."""
        calls_raw = self.r.get(f"massive:gex:model:{symbol}:calls")
        puts_raw = self.r.get(f"massive:gex:model:{symbol}:puts")

        return {
            "calls": self._safe_json(calls_raw),
            "puts": self._safe_json(puts_raw),
        }

    def get_heatmap(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get heatmap model for a symbol."""
        raw = self.r.get(f"massive:heatmap:model:{symbol}:latest")
        return self._safe_json(raw)

    def _compute_gex_bias(self, gex: Dict[str, Any], spot: float) -> Dict[str, Any]:
        """
        Compute GEX bias relative to spot.
        Returns gamma regime and key levels.
        """
        calls = gex.get("calls") or {}
        puts = gex.get("puts") or {}

        calls_exp = calls.get("expirations", {})
        puts_exp = puts.get("expirations", {})

        if not calls_exp:
            return {"regime": "unknown", "net_gex": 0, "key_levels": []}

        # Use first expiration (0-DTE)
        exp_key = next(iter(calls_exp), None)
        if not exp_key:
            return {"regime": "unknown", "net_gex": 0, "key_levels": []}

        call_gex = calls_exp.get(exp_key, {})
        put_gex = puts_exp.get(exp_key, {}) if exp_key in puts_exp else {}

        # Calculate net GEX at spot
        spot_strike = str(int(round(spot / 5) * 5))  # Round to nearest 5
        call_at_spot = call_gex.get(spot_strike, 0)
        put_at_spot = put_gex.get(spot_strike, 0)
        net_gex = call_at_spot - put_at_spot

        # Find key levels (largest absolute GEX)
        all_strikes = set(call_gex.keys()) | set(put_gex.keys())
        gex_by_strike = []
        for s in all_strikes:
            try:
                strike = int(s)
                c = call_gex.get(s, 0)
                p = put_gex.get(s, 0)
                net = c - p
                gex_by_strike.append((strike, net, abs(net)))
            except ValueError:
                continue

        # Sort by absolute GEX
        gex_by_strike.sort(key=lambda x: x[2], reverse=True)
        key_levels = [(s, net) for s, net, _ in gex_by_strike[:5]]

        # Determine regime
        if net_gex > 0:
            regime = "positive_gamma"
        elif net_gex < 0:
            regime = "negative_gamma"
        else:
            regime = "neutral"

        return {
            "regime": regime,
            "net_gex": net_gex,
            "key_levels": key_levels,
            "expiration": exp_key,
        }

    def _compute_heatmap_levels(self, heatmap: Dict[str, Any], spot: float) -> Dict[str, Any]:
        """
        Extract key convexity levels from heatmap near spot.
        """
        tiles = heatmap.get("tiles", {})
        if not tiles:
            return {"sweet_spots": [], "danger_zones": []}

        # Find butterfly tiles with best value (lowest debit near spot)
        butterflies = []
        for tile_key, tile in tiles.items():
            if not tile_key.startswith("butterfly:"):
                continue
            parts = tile_key.split(":")
            if len(parts) != 4:
                continue
            _, dte, width, strike = parts
            try:
                strike_val = int(strike)
                # Only consider strikes within 100 pts of spot
                if abs(strike_val - spot) > 100:
                    continue
                call_debit = tile.get("call", {}).get("debit")
                put_debit = tile.get("put", {}).get("debit")
                if call_debit is not None:
                    butterflies.append({
                        "strike": strike_val,
                        "width": int(width),
                        "dte": int(dte),
                        "side": "call",
                        "debit": call_debit,
                    })
                if put_debit is not None:
                    butterflies.append({
                        "strike": strike_val,
                        "width": int(width),
                        "dte": int(dte),
                        "side": "put",
                        "debit": put_debit,
                    })
            except ValueError:
                continue

        # Sort by debit (lower is better for butterflies)
        butterflies.sort(key=lambda x: x["debit"])

        # Sweet spots = cheapest butterflies (high convexity)
        sweet_spots = butterflies[:3] if butterflies else []

        return {
            "sweet_spots": sweet_spots,
            "total_tiles": len(tiles),
        }

    def get_market_state(self) -> Dict[str, Any]:
        """
        Get comprehensive market state for epoch commentary.
        """
        state = {
            "ts": None,
            "spots": {},
            "gex": {},
            "heatmap": {},
        }

        # Spot prices
        for symbol in self.SYMBOLS:
            spot_data = self.get_spot(symbol)
            if spot_data:
                state["spots"][symbol] = {
                    "value": spot_data.get("value"),
                    "change": spot_data.get("change"),
                    "change_pct": spot_data.get("change_pct"),
                }

        # GEX and heatmap for SPX and NDX
        for symbol in ["I:SPX", "I:NDX"]:
            spot_val = state["spots"].get(symbol, {}).get("value")
            if not spot_val:
                continue

            # GEX
            gex = self.get_gex(symbol)
            if gex.get("calls") or gex.get("puts"):
                state["gex"][symbol] = self._compute_gex_bias(gex, spot_val)

            # Heatmap
            heatmap = self.get_heatmap(symbol)
            if heatmap:
                state["heatmap"][symbol] = self._compute_heatmap_levels(heatmap, spot_val)

        return state
