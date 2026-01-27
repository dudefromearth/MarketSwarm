#!/usr/bin/env python3
"""
epochs.py — Epoch schedule and commentary generation for Vexy AI

Epochs are the canonical trading day segments that trigger scheduled commentary.
Commentary is enriched with real-time market data from Massive.
"""

import os
from datetime import datetime
from typing import Any, Dict, Optional

# =============================================================================
# CANONICAL EPOCH SCHEDULE — THE TRUTH OF THE TRADING DAY
# =============================================================================
# Times are in ET. This list is sacred.
EPOCHS = [
    {
        "name": "Premarket",
        "time": "08:00",
        "context": "Pre-market session. Futures setting the tone. Watch overnight developments.",
    },
    {
        "name": "Post-Open",
        "time": "09:35",
        "context": "Opening rotation complete. Initial direction established. Volume normalizing.",
    },
    {
        "name": "European Close",
        "time": "11:30",
        "context": "European markets closing. Cross-Atlantic flows shifting. Mid-morning inflection.",
    },
    {
        "name": "Lunch Vol Crush",
        "time": "13:00",
        "context": "Lunch hour volatility compression. Low participation. Watch for mean reversion setups.",
    },
    {
        "name": "Commodity Shadow",
        "time": "14:00",
        "context": "Commodity markets closing. Energy and metals flows impacting equity correlation.",
    },
    {
        "name": "Power Hour Begins",
        "time": "15:00",
        "context": "Final hour approaching. Institutional repositioning. Volume acceleration.",
    },
    {
        "name": "Into the Close",
        "time": "15:50",
        "context": "Closing imbalances revealing. MOC orders driving final moves. Gamma intensifying.",
    },
    {
        "name": "Post-Close Wrap",
        "time": "16:01",
        "context": "Cash session closed. Reviewing the day. After-hours positioning.",
    },
]


def should_speak_epoch(current_time: str) -> Optional[Dict[str, str]]:
    """
    Determine if Vexy should deliver scheduled epoch commentary.
    Returns the most recent epoch that has triggered.
    """
    force = os.getenv("FORCE_EPOCH", "false").lower() == "true"

    if force:
        return EPOCHS[0]

    # Find the latest epoch that has triggered (reverse search)
    active_epoch = None
    for epoch in EPOCHS:
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

    Args:
        epoch: The epoch definition (name, time, context)
        market_state: Current market state from MarketReader

    Returns:
        Human-readable commentary string
    """
    name = epoch["name"]
    context = epoch.get("context", "")
    date_str = datetime.now().strftime("%A, %B %d")

    spots = market_state.get("spots", {})
    gex = market_state.get("gex", {})
    heatmap = market_state.get("heatmap", {})

    # Build commentary sections
    sections = []

    # Header
    sections.append(f"**{name}** — {date_str}")

    # Context
    if context:
        sections.append(context)

    # Spot prices
    spot_text = _format_spot(spots)
    if spot_text and spot_text != "Spot data unavailable":
        sections.append(f"Markets: {spot_text}.")

    # VIX
    vix_data = spots.get("I:VIX")
    if vix_data and vix_data.get("value"):
        vix = vix_data["value"]
        if vix > 25:
            sections.append(f"VIX elevated at {vix:.1f} — heightened fear, expect wider swings.")
        elif vix < 15:
            sections.append(f"VIX subdued at {vix:.1f} — complacency zone, watch for vol expansion.")
        else:
            sections.append(f"VIX at {vix:.1f} — normal range.")

    # GEX regime
    gex_text = _format_gex(gex)
    if gex_text:
        sections.append(gex_text)

    # Heatmap opportunities
    heatmap_text = _format_heatmap(heatmap, spots)
    if heatmap_text:
        sections.append(f"Convexity: {heatmap_text}")

    return " ".join(sections)
