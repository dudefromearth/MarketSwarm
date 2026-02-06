"""
Dealer Gravity Analysis Prompts - AI prompt templates for visual chart analysis.

Uses Claude Vision API to analyze Dealer Gravity charts and detect structural features.

IMPORTANT: This module uses Dealer Gravity lexicon exclusively.

Canonical Terminology:
    - Volume Node: Price level with concentrated market attention (NOT HVN)
    - Volume Well: Price level with neglect (NOT LVN)
    - Crevasse: Extended region of persistent volume scarcity
    - Market Memory: Persistent topology across long horizons

BANNED TERMS (never use): POC, VAH, VAL, Value Area, HVN, LVN, or any AMT terminology
"""

from typing import Dict, Any, Optional


# ========== System Prompt ==========

DG_ANALYSIS_SYSTEM_PROMPT = """You are an expert visual analyst for Dealer Gravity charts in the MarketSwarm trading platform.

YOUR ROLE:
- Analyze chart screenshots to identify structural features
- Use Dealer Gravity terminology EXCLUSIVELY
- Provide objective, data-driven observations

DEALER GRAVITY LEXICON (REQUIRED - use ONLY these terms):
- Volume Node: Price level where market participation concentrated (attention, friction, Market Memory)
- Volume Well: Price level with absence of engagement (neglect, low resistance, acceleration zones)
- Crevasse: Extended regions of persistent volume scarcity (structural voids, convex outcome zones, rapid traversal)
- Market Memory: Persistent topology revealed by transformed volume across long horizons

BANNED TERMS (NEVER use these - they are incorrect for this framework):
- POC (Point of Control)
- VAH / VAL (Value Area High/Low)
- Value Area
- HVN / LVN (High/Low Volume Nodes)
- Any Auction Market Theory terminology

CONCEPTUAL FRAMEWORK:
- Dealer Gravity does NOT model value or equilibrium
- It models ATTENTION, NEGLECT, and MEMORY
- Volume Nodes represent where the market has paid attention (friction)
- Volume Wells represent where the market has shown neglect (acceleration)
- Crevasses are structural voids where convexity emerges
- Market Memory persists across long horizons, decays slowly

OUTPUT FORMAT:
Return a JSON object with the following structure:
{
    "volume_nodes": [<price levels>],
    "volume_wells": [<price levels>],
    "crevasses": [[<start_price>, <end_price>], ...],
    "market_memory_strength": <0.0-1.0>,
    "bias": "bullish" | "bearish" | "neutral",
    "summary": "<1-2 sentence observation>"
}

ANALYSIS GUIDELINES:
- Volume Nodes: Look for price levels with tall histogram bars (concentrated attention)
- Volume Wells: Look for price levels with short or absent bars (neglect)
- Crevasses: Look for extended regions (3+ levels) of very low volume
- Market Memory Strength: Higher when volume distribution is clearly defined with distinct nodes
- Bias: Based on where current price sits relative to major nodes
"""


# ========== Analysis Prompts ==========

def get_dg_analysis_prompt(data: Dict[str, Any]) -> str:
    """
    Generate prompt for Dealer Gravity chart analysis.

    Args:
        data: Dictionary containing:
            - spot_price: Current spot price
            - symbol: Trading symbol (e.g., "SPX")
            - timeframe: Chart timeframe if available

    Returns:
        Prompt string for Claude Vision API
    """
    spot_price = data.get("spot_price")
    symbol = data.get("symbol", "SPX")
    timeframe = data.get("timeframe", "composite")

    spot_context = f"Current spot price is {spot_price:.2f}." if spot_price else ""

    return f"""Analyze this Dealer Gravity chart for {symbol} ({timeframe} view).

{spot_context}

Identify and return:
1. Volume Nodes: Price levels with concentrated market attention (look for tall histogram bars)
2. Volume Wells: Price levels with neglect (look for short or absent bars)
3. Crevasses: Extended regions of persistent volume scarcity (3+ consecutive low-volume levels)
4. Market Memory Strength: How clearly defined is the volume structure (0.0-1.0)
5. Bias: Is spot closer to support nodes (bullish) or resistance nodes (bearish), or balanced (neutral)

Important:
- Use Dealer Gravity terminology ONLY (Volume Node, Volume Well, Crevasse, Market Memory)
- NEVER use terms like POC, VAH, VAL, HVN, LVN, or Value Area
- Return only the JSON object, no additional text
"""


def get_dg_gex_combined_prompt(data: Dict[str, Any]) -> str:
    """
    Generate prompt for combined Dealer Gravity + GEX analysis.

    Args:
        data: Dictionary containing:
            - spot_price: Current spot price
            - symbol: Trading symbol
            - gex_flip_point: GEX zero-gamma level if available

    Returns:
        Prompt string for combined DG+GEX analysis
    """
    spot_price = data.get("spot_price")
    symbol = data.get("symbol", "SPX")
    gex_flip = data.get("gex_flip_point")

    context_parts = []
    if spot_price:
        context_parts.append(f"Current spot: {spot_price:.2f}")
    if gex_flip:
        context_parts.append(f"GEX flip point: {gex_flip:.2f}")

    context = ". ".join(context_parts) + "." if context_parts else ""

    return f"""Analyze this combined Dealer Gravity and GEX chart for {symbol}.

{context}

For Dealer Gravity analysis:
1. Identify Volume Nodes (concentrated attention)
2. Identify Volume Wells (neglect zones)
3. Identify Crevasses (extended scarcity regions)
4. Assess Market Memory strength

For GEX integration:
1. Note gamma alignment (positive/negative relative to spot)
2. Identify if spot is near call walls or put walls
3. Note any confluence between GEX levels and Dealer Gravity structures

Return JSON with this structure:
{{
    "volume_nodes": [<prices>],
    "volume_wells": [<prices>],
    "crevasses": [[<start>, <end>], ...],
    "market_memory_strength": <0.0-1.0>,
    "gamma_alignment": "positive" | "negative",
    "gex_call_wall": <price or null>,
    "gex_put_wall": <price or null>,
    "bias": "bullish" | "bearish" | "neutral",
    "summary": "<observation about DG + GEX confluence>"
}}

IMPORTANT: Use only Dealer Gravity terminology. Never use POC, VAH, VAL, HVN, LVN.
"""


def get_dg_trade_context_prompt(data: Dict[str, Any]) -> str:
    """
    Generate prompt for trade context analysis.

    Provides quick context for Trade Selector scoring based on
    Dealer Gravity structural features.

    Args:
        data: Dictionary containing:
            - spot_price: Current spot price
            - entry_strike: Proposed entry strike
            - symbol: Trading symbol

    Returns:
        Prompt for trade context assessment
    """
    spot_price = data.get("spot_price")
    entry_strike = data.get("entry_strike")
    symbol = data.get("symbol", "SPX")

    return f"""Quick structural context check for {symbol}.

Spot: {spot_price:.2f}
Proposed entry: {entry_strike}

Assess:
1. Is the entry near a Volume Node? (friction - may slow price movement)
2. Is the entry in a Volume Well? (acceleration potential)
3. Is the entry within a Crevasse? (convexity opportunity)
4. What is the nearest Volume Node distance (as % of spot)?

Return compact JSON:
{{
    "entry_near_node": true|false,
    "entry_in_well": true|false,
    "entry_in_crevasse": true|false,
    "nearest_node_dist_pct": <number>,
    "structural_quality": "favorable" | "neutral" | "challenging"
}}

Use Dealer Gravity terminology only.
"""


# ========== Response Parsing ==========

def parse_dg_analysis_response(response_text: str) -> Optional[Dict[str, Any]]:
    """
    Parse Claude's response into structured data.

    Args:
        response_text: Raw response from Claude Vision API

    Returns:
        Parsed dictionary or None if parsing fails
    """
    import json
    import re

    # Try to extract JSON from response
    # Claude sometimes wraps JSON in markdown code blocks
    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response_text)
    if json_match:
        json_str = json_match.group(1)
    else:
        # Try to find raw JSON object
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            json_str = json_match.group(0)
        else:
            return None

    try:
        result = json.loads(json_str)

        # Validate required fields
        required_fields = ["volume_nodes", "volume_wells", "crevasses"]
        for field in required_fields:
            if field not in result:
                result[field] = []

        # Ensure numeric fields
        result["market_memory_strength"] = float(result.get("market_memory_strength", 0.5))

        # Validate bias
        if result.get("bias") not in ["bullish", "bearish", "neutral"]:
            result["bias"] = "neutral"

        return result

    except json.JSONDecodeError:
        return None
