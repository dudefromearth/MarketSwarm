#!/usr/bin/env python3
"""
epochs.py — Immutable epoch schedule for Vexy AI Play-by-Play Engine

Part of MarketSwarm — the real-time options + intel play-by-play engine
Built by Ernie & Conor — 2025

Purpose:
    Define the exact daily trading epochs that trigger scheduled commentary.

Key Responsibilities:
    • Provide the canonical list of market epochs and their trigger times
    • Determine if current time falls within an active epoch window
    • Support FORCE_EPOCH for debugging and immediate commentary

First Principles:
    • Epochs are immutable truth — no dynamic loading, no config drift
    • Time comparison is simple string >= check (ET assumed)
    • Once an epoch fires, it speaks only once per day
    • FORCE_EPOCH bypasses time checks for testing

Future Developer Notes:
    • All times are Eastern Time (ET) — market standard
    • Condition field reserved for future economic calendar integration
    • Never change this file unless the market structure changes
    • This is the heartbeat of the trading day — treat with reverence

You are holding the rhythm of the market.
Respect it.
"""

import os
from datetime import datetime
from typing import Dict, Optional

# =============================================================================
# CANONICAL EPOCH SCHEDULE — THE TRUTH OF THE TRADING DAY
# =============================================================================
# Times are in ET. This list is sacred.
EPOCHS = [
    {"name": "Premarket", "time": "08:00", "condition": "before_reports"},
    {"name": "Post-Reports Premarket", "time": "08:35", "condition": "after_reports"},
    {"name": "Post-Open", "time": "09:35"},
    {"name": "European Close", "time": "11:30"},
    {"name": "Lunch Vol Crush", "time": "13:00"},
    {"name": "Commodity Shadow", "time": "14:00"},
    {"name": "Power Hour Begins", "time": "15:00"},
    {"name": "Into the Close", "time": "15:50"},
    {"name": "Post-Close Wrap", "time": "16:01"},
]


def should_speak_epoch(current_time: str) -> Optional[Dict[str, str]]:
    """
    Determine if Vexy should deliver scheduled epoch commentary.

    Checks current time against the canonical EPOCHS list.
    Returns commentary payload if an epoch window is active.

    Args:
        current_time (str): Current time in "HH:MM" format (24-hour, ET)

    Returns:
        dict | None: Epoch payload with name and commentary if should speak,
                     None otherwise

    Notes:
        • Uses simple string comparison — reliable and deterministic
        • FORCE_EPOCH=true bypasses time check (debug only)
        • Each epoch speaks exactly once per day
        • Condition field reserved for future calendar integration
    """
    force = os.getenv("FORCE_EPOCH", "false").lower() == "true"

    if force:
        # Return first epoch immediately for testing
        epoch = EPOCHS[0]
    else:
        for epoch in EPOCHS:
            if current_time >= epoch["time"]:
                return {
                    "name": epoch["name"],
                    "commentary": f"This is {epoch['name']} on {datetime.now().strftime('%Y-%m-%d')}. "
                                  f"Market is in {epoch['name'].lower()} regime."
                }
    return None