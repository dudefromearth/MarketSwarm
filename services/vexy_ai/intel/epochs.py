#!/usr/bin/env python3
"""
epochs.py — Epoch schedule and commentary generation for Vexy AI

Epochs are the canonical trading day segments that trigger scheduled commentary.
Commentary is enriched with real-time market data from Massive.

Epochs are defined in truth/components/vexy_ai.json and passed via config.
"""

import os
from datetime import datetime
from typing import Any, Dict, List, Optional


def should_speak_epoch(current_time: str, epochs: List[Dict[str, str]]) -> Optional[Dict[str, str]]:
    """
    Determine if Vexy should deliver scheduled epoch commentary.
    Returns the most recent epoch that has triggered.

    Args:
        current_time: Current time as HH:MM string (ET)
        epochs: List of epoch definitions from config
    """
    if not epochs:
        return None

    force = os.getenv("FORCE_EPOCH", "false").lower() == "true"

    if force:
        return epochs[0]

    # Find the latest epoch that has triggered (reverse search)
    active_epoch = None
    for epoch in epochs:
        if current_time >= epoch["time"]:
            active_epoch = epoch

    return active_epoch


def _format_spot(spots: Dict[str, Any]) -> str:
    """Format spot prices for commentary."""
    parts = []
    for symbol, data in spots.items():
        if not data or data.get("value") is None:
            continue
        val = data["value"]
        change = data.get("change_pct")
        name = symbol.replace("I:", "")
        if change is not None:
            direction = "up" if change > 0 else "down" if change < 0 else "flat"
            parts.append(f"{name} at {val:.2f} ({direction} {abs(change):.2f}%)")
        else:
            parts.append(f"{name} at {val:.2f}")
    return "; ".join(parts) if parts else "Spot data unavailable"


def _format_gex(gex: Dict[str, Any]) -> str:
    """Format GEX regime for commentary."""
    parts = []
    for symbol, data in gex.items():
        if not data:
            continue
        regime = data.get("regime", "unknown")
        name = symbol.replace("I:", "")

        if regime == "positive_gamma":
            parts.append(f"{name} in positive gamma — dealers hedging dampens moves")
        elif regime == "negative_gamma":
            parts.append(f"{name} in negative gamma — dealers amplify moves, volatility risk elevated")
        else:
            parts.append(f"{name} gamma neutral")

        # Add key level if available
        key_levels = data.get("key_levels", [])
        if key_levels:
            top_level, top_gex = key_levels[0]
            parts.append(f"Key GEX level at {top_level}")

    return ". ".join(parts) if parts else ""


def _format_heatmap(heatmap: Dict[str, Any], spots: Dict[str, Any]) -> str:
    """Format heatmap sweet spots for commentary."""
    parts = []
    for symbol, data in heatmap.items():
        if not data:
            continue
        sweet_spots = data.get("sweet_spots", [])
        if not sweet_spots:
            continue

        name = symbol.replace("I:", "")
        spot_val = spots.get(symbol, {}).get("value")

        # Best butterfly opportunity
        best = sweet_spots[0]
        strike = best["strike"]
        width = best["width"]
        debit = best["debit"]
        side = best["side"]

        if spot_val:
            distance = strike - spot_val
            direction = "above" if distance > 0 else "below"
            parts.append(
                f"{name} convexity sweet spot: {width}-wide {side} butterfly at {strike} "
                f"({abs(distance):.0f} pts {direction} spot) for ${debit:.2f} debit"
            )

    return ". ".join(parts) if parts else ""


def generate_epoch_commentary(epoch: Dict[str, str], market_state: Dict[str, Any]) -> str:
    """
    Generate rich epoch commentary incorporating market data.

    Uses standard Vexy markdown format:
    - Blockquote for context
    - Bold headers for sections
    - Bullet lists for data
    - Bottom line takeaway

    Args:
        epoch: The epoch definition (name, time, context)
        market_state: Current market state from MarketReader

    Returns:
        Markdown-formatted commentary string
    """
    name = epoch["name"]
    context = epoch.get("context", "")

    spots = market_state.get("spots", {})
    gex = market_state.get("gex", {})
    heatmap = market_state.get("heatmap", {})

    lines = []

    # Context as blockquote
    if context:
        lines.append(f"> {context}")
        lines.append("")

    # Levels section
    level_items = []
    for symbol, data in spots.items():
        if not data or data.get("value") is None:
            continue
        val = data["value"]
        change = data.get("change_pct")
        sym = symbol.replace("I:", "")
        if change is not None:
            sign = "+" if change > 0 else ""
            level_items.append(f"- {sym}: {val:,.2f} ({sign}{change:.2f}%)")
        else:
            level_items.append(f"- {sym}: {val:,.2f}")

    if level_items:
        lines.append("**Levels**")
        lines.extend(level_items)
        lines.append("")

    # Structure section (GEX + VIX regime)
    structure_items = []

    # VIX regime
    vix_data = spots.get("I:VIX")
    if vix_data and vix_data.get("value"):
        vix = vix_data["value"]
        if vix > 25:
            structure_items.append(f"- VIX elevated at {vix:.1f} — wider swings expected")
        elif vix < 15:
            structure_items.append(f"- VIX subdued at {vix:.1f} — complacency zone")
        else:
            structure_items.append(f"- VIX at {vix:.1f} — normal range")

    # GEX regime
    for symbol, data in gex.items():
        if not data:
            continue
        regime = data.get("regime", "")
        sym = symbol.replace("I:", "")
        if regime == "positive_gamma":
            structure_items.append(f"- {sym} positive gamma — dealers dampen moves")
        elif regime == "negative_gamma":
            structure_items.append(f"- {sym} negative gamma — dealers amplify moves")

        key_levels = data.get("key_levels", [])
        if key_levels:
            top_level, _ = key_levels[0]
            structure_items.append(f"- Key GEX wall at {int(top_level)}")

    if structure_items:
        lines.append("**Structure**")
        lines.extend(structure_items)
        lines.append("")

    # Convexity section (heatmap sweet spots)
    convexity_items = []
    for symbol, data in heatmap.items():
        if not data:
            continue
        sweet_spots = data.get("sweet_spots", [])
        if not sweet_spots:
            continue

        spot_val = spots.get(symbol, {}).get("value")
        best = sweet_spots[0]
        strike = best["strike"]
        width = best["width"]
        debit = best["debit"]
        side = best["side"]

        if spot_val:
            distance = abs(strike - spot_val)
            direction = "above" if strike > spot_val else "below"
            convexity_items.append(
                f"- {width}w {side} fly at {strike} ({distance:.0f} pts {direction}) — ${debit:.2f}"
            )

    if convexity_items:
        lines.append("**Convexity**")
        lines.extend(convexity_items)
        lines.append("")

    # Bottom line
    bottom_line = _generate_bottom_line(spots, gex)
    lines.append(f"**Bottom line:** {bottom_line}")

    return "\n".join(lines)


def _generate_bottom_line(spots: Dict[str, Any], gex: Dict[str, Any]) -> str:
    """Generate a brief bottom line takeaway based on market state."""
    vix_data = spots.get("I:VIX", {})
    vix = vix_data.get("value", 20) if vix_data else 20

    # Determine gamma regime
    gamma_regime = "neutral"
    for data in gex.values():
        if data:
            regime = data.get("regime", "")
            if regime in ("positive_gamma", "negative_gamma"):
                gamma_regime = regime
                break

    if vix > 30:
        return "Elevated vol — wide flies, patient entries."
    elif vix < 15:
        if gamma_regime == "positive_gamma":
            return "Low vol, positive gamma — range-bound, narrow flies."
        return "Subdued vol — watch for expansion."
    elif gamma_regime == "negative_gamma":
        return "Negative gamma zone — expect amplified moves."
    elif gamma_regime == "positive_gamma":
        return "Positive gamma — dealers dampen, structure holds."
    else:
        return "Standard conditions — follow the structure."
