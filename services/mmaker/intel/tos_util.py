# services/mmaker/intel/tos_util.py

"""
Unified ThinkOrSwim order-script utility for:
    • Single Calls / Puts
    • Vertical Spreads
    • Butterflies (1–2–1)

This is intentionally "loose completeness":
    - Missing legs produce a partial script with warnings
    - The transformer always gets *something*, never fails
    - You can refine exact ToS syntax later
"""

from __future__ import annotations
from typing import List, Dict, Any, Optional


# =====================================================================================
# Helpers
# =====================================================================================

def _fmt_leg(leg: Dict[str, Any]) -> str:
    """Format a single option leg into a ToS-style text component."""
    side = leg.get("side", "long")
    qty = leg.get("qty", 1)
    right = leg.get("right", "?")
    strike = leg.get("strike", "?")
    exp = leg.get("exp", "????-??-??")

    action = "BUY" if side == "long" else "SELL"

    return f"{action} {qty} {exp} {strike}{right}"


def _legs_to_multiline(legs: List[Dict[str, Any]]) -> str:
    """Simple pretty-printing for multi-leg structures."""
    return "\n".join("  " + _fmt_leg(l) for l in legs)


def _script_header(strategy_type: str) -> str:
    return f"# TOS ORDER: {strategy_type.upper()}\n"


# =====================================================================================
# SINGLE CONTRACT SCRIPT
# =====================================================================================

def tos_single(right: str, strike: float, exp: str) -> Dict[str, Any]:
    """
    For raw call/put tiles.

    Example:
        BUY 1 2025-12-10 4800C
    """
    leg = {
        "side": "long",
        "qty": 1,
        "right": right.upper(),
        "strike": strike,
        "exp": exp,
    }

    script = (
        _script_header("single") +
        _fmt_leg(leg)
    )

    return {
        "script": script,
        "legs": [leg],
        "description": f"Single option: {strike}{right.upper()} exp {exp}",
    }


# =====================================================================================
# VERTICAL SCRIPT
# =====================================================================================

def tos_vertical(legs: List[Dict[str, Any]], width: float) -> Dict[str, Any]:
    """
    Vertical spread (long K, short K±W).
    Legs MUST be 2, but we allow incomplete input gracefully.
    """
    if len(legs) < 2:
        script = (
            _script_header("vertical") +
            "# INCOMPLETE VERTICAL — missing legs\n" +
            _legs_to_multiline(legs)
        )
        return {
            "script": script,
            "legs": legs,
            "description": "Incomplete vertical spread (waiting on missing legs).",
        }

    script = (
        _script_header("vertical") +
        _legs_to_multiline(legs)
    )

    desc = (
        f"Vertical spread width={width}, "
        f"{legs[0]['strike']}→{legs[1]['strike']} ({legs[0]['right']})"
    )

    return {
        "script": script,
        "legs": legs,
        "description": desc,
    }


# =====================================================================================
# BUTTERFLY SCRIPT (1–2–1)
# =====================================================================================

def tos_butterfly(legs: List[Dict[str, Any]], center: float, width: float) -> Dict[str, Any]:
    """
    Butterfly legs must be [long, short, long].
    But incomplete structures still produce a partial script.
    """
    if len(legs) < 3:
        script = (
            _script_header("butterfly") +
            "# INCOMPLETE BUTTERFLY — missing legs\n" +
            _legs_to_multiline(legs)
        )
        return {
            "script": script,
            "legs": legs,
            "description": f"Incomplete butterfly (missing 1–2–1 legs), center={center}, width={width}",
        }

    script = (
        _script_header("butterfly") +
        _legs_to_multiline(legs)
    )

    desc = (
        f"Butterfly: center={center}, width={width}, right={legs[0]['right']}"
    )

    return {
        "script": script,
        "legs": legs,
        "description": desc,
    }


# =====================================================================================
# MULTI-STRATEGY DISPATCH
# =====================================================================================

def tos_script_from_legs(legs: List[Dict[str, Any]], meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Generic wrapper:
        meta = {
            'strategy': 'single' | 'vertical' | 'butterfly',
            'width': float,
            'center': float,
            ...
        }

    Transformers call this with:
        tos_script_from_legs(legs, tile_meta)
    """
    if meta is None:
        meta = {}

    strategy = meta.get("strategy", "").lower()

    if strategy == "single":
        return tos_single(
            right=legs[0]["right"] if legs else "?",
            strike=legs[0]["strike"] if legs else None,
            exp=legs[0]["exp"] if legs else None,
        )

    if strategy == "vertical":
        return tos_vertical(
            legs=legs,
            width=meta.get("width", 0),
        )

    if strategy == "butterfly":
        return tos_butterfly(
            legs=legs,
            center=meta.get("center", None),
            width=meta.get("width", None),
        )

    # fallback raw script
    return {
        "script": _script_header("unknown") + _legs_to_multiline(legs),
        "legs": legs,
        "description": "Unknown strategy",
    }