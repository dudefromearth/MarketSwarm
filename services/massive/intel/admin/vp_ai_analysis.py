#!/usr/bin/env python3
"""
VP AI Analysis - Claude Vision-based structural analysis for Dealer Gravity

Uses Claude's vision capabilities to analyze volume profile charts and
identify structural elements using the Dealer Gravity lexicon.

Dealer Gravity Lexicon (Authoritative):
  - Volume Node: Concentrated market attention (friction, memory)
  - Volume Well: Market neglect (low resistance, acceleration zone)
  - Crevasse: Extended scarcity region (structural void, convexity zone)
  - Market Memory: Persistent topology across time horizons
"""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, List

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False


def get_anthropic_api_key() -> str:
    """Get Anthropic API key from environment or truth.json config."""
    # First check environment
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if key:
        return key

    # Try to load from truth.json (MarketSwarm config)
    try:
        import json
        from pathlib import Path

        # Look for truth.json in common locations
        possible_paths = [
            Path(__file__).parent.parent.parent.parent.parent / "scripts" / "truth.json",
            Path(__file__).parent.parent.parent.parent.parent / "truth.json",
            Path.home() / "MarketSwarm" / "scripts" / "truth.json",
        ]

        for config_path in possible_paths:
            if config_path.exists():
                with open(config_path) as f:
                    config = json.load(f)
                    key = config.get("env", {}).get("ANTHROPIC_API_KEY", "")
                    if key:
                        return key
    except Exception:
        pass

    return ""


ANTHROPIC_API_KEY = get_anthropic_api_key()

# Analysis prompt using Dealer Gravity lexicon
ANALYSIS_PROMPT = """You are an expert in Dealer Gravity analysis - identifying market structure through volume distribution patterns.

## Your Task

Look at this SPX Volume Profile chart. Identify ALL the **transition edges** - price levels where volume changes significantly from high to low or low to high.

These transition edges represent:
- **Institutional battle zones** - Where large players have stacked orders
- **Order flow imbalances** - Sharp volume changes show where pressure shifts
- **Natural support/resistance** - Price reacts at these boundaries

## What To Look For

1. **Volume Edges** - Every price where volume transitions sharply:
   - Where a volume cluster STARTS (volume rising from low)
   - Where a volume cluster ENDS (volume dropping off)
   - Both sides of valleys/cracks in the profile
   - Any clear demarcation between high and low volume

2. **Crevasses** - Deep cracks/valleys in the profile:
   - Extended low-volume regions between clusters
   - "Air pockets" where price can move quickly
   - Return as [start_price, end_price] ranges

## Output Format

Return JSON with ALL edges you can see (aim for 20-40 edges in a typical range):

```json
{
  "volume_nodes": [6250, 6280, 6310, 6340, ...],
  "crevasses": [[6500, 6545], [6720, 6755], ...],
  "analysis": "Brief description of the structure"
}
```

IMPORTANT:
- List EVERY transition edge you can see, not just the major ones
- Use whole dollar amounts for SPX
- Be thorough - if you can see a transition, include it
- Edges are NOT peaks - they're the boundaries where volume changes
"""


def log(stage: str, emoji: str, msg: str) -> None:
    print(f"[vp_ai|{stage}]{emoji} {msg}")


def encode_image(image_path: str) -> str:
    """Encode image to base64."""
    with open(image_path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def analyze_chart_with_claude(
    image_path: str,
    model: str = "claude-sonnet-4-20250514",
) -> Dict[str, Any] | None:
    """
    Send volume profile chart to Claude for structural analysis.

    Returns parsed JSON with identified structures, or None on failure.
    """
    if not HAS_ANTHROPIC:
        log("ai", "❌", "anthropic package not installed. Run: pip install anthropic")
        return None

    api_key = ANTHROPIC_API_KEY
    if not api_key:
        log("ai", "❌", "ANTHROPIC_API_KEY not set")
        return None

    if not Path(image_path).exists():
        log("ai", "❌", f"Image not found: {image_path}")
        return None

    log("ai", "🤖", f"Analyzing chart with Claude ({model})...")

    try:
        client = anthropic.Anthropic(api_key=api_key)

        # Encode image
        image_data = encode_image(image_path)

        # Determine media type
        ext = Path(image_path).suffix.lower()
        media_type = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }.get(ext, "image/png")

        # Send to Claude
        message = client.messages.create(
            model=model,
            max_tokens=2000,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_data,
                            },
                        },
                        {
                            "type": "text",
                            "text": ANALYSIS_PROMPT,
                        },
                    ],
                }
            ],
        )

        # Extract response text
        response_text = message.content[0].text
        log("ai", "✅", f"Received response ({message.usage.input_tokens} in, {message.usage.output_tokens} out)")

        # Parse JSON from response
        result = parse_ai_response(response_text)

        if result:
            result["model"] = model
            result["analyzed_at"] = datetime.now(UTC).isoformat()
            result["tokens_used"] = message.usage.input_tokens + message.usage.output_tokens

        return result

    except anthropic.APIError as e:
        log("ai", "❌", f"API error: {e}")
        return None
    except Exception as e:
        log("ai", "❌", f"Error: {e}")
        return None


def parse_ai_response(response_text: str) -> Dict[str, Any] | None:
    """Parse JSON from Claude's response."""
    try:
        # Try to find JSON block in response
        if "```json" in response_text:
            start = response_text.find("```json") + 7
            end = response_text.find("```", start)
            json_str = response_text[start:end].strip()
        elif "```" in response_text:
            start = response_text.find("```") + 3
            end = response_text.find("```", start)
            json_str = response_text[start:end].strip()
        else:
            # Try to parse entire response as JSON
            json_str = response_text.strip()

        result = json.loads(json_str)

        # Validate expected fields
        if "volume_nodes" not in result:
            result["volume_nodes"] = []
        if "volume_wells" not in result:
            result["volume_wells"] = []
        if "crevasses" not in result:
            result["crevasses"] = []

        return result

    except json.JSONDecodeError as e:
        log("ai", "⚠️", f"Failed to parse JSON: {e}")
        # Return raw analysis as fallback
        return {
            "volume_nodes": [],
            "volume_wells": [],
            "crevasses": [],
            "analysis": response_text,
            "parse_error": str(e),
        }


def print_ai_analysis(result: Dict[str, Any]) -> None:
    """Pretty print AI analysis results."""
    print("\n" + "=" * 70)
    print("AI STRUCTURAL ANALYSIS (Claude Vision)")
    print("=" * 70)

    if result.get("parse_error"):
        print(f"\n⚠️  Warning: JSON parsing failed - showing raw analysis")
        print(f"\n{result.get('analysis', 'No analysis available')}")
        return

    print(f"\nModel: {result.get('model', 'unknown')}")
    print(f"Tokens: {result.get('tokens_used', 'unknown')}")

    print("\n📍 VOLUME NODES (Concentrated Attention):")
    nodes = result.get("volume_nodes", [])
    if nodes:
        for i, price in enumerate(nodes, 1):
            print(f"   {i}. ${price:,}")
    else:
        print("   None identified")

    print("\n📍 VOLUME WELLS (Market Neglect):")
    wells = result.get("volume_wells", [])
    if wells:
        for i, price in enumerate(wells, 1):
            print(f"   {i}. ${price:,}")
    else:
        print("   None identified")

    print("\n📍 CREVASSES (Structural Voids):")
    crevasses = result.get("crevasses", [])
    if crevasses:
        for i, (start, end) in enumerate(crevasses, 1):
            print(f"   {i}. ${start:,} to ${end:,} (${end - start} range)")
    else:
        print("   None identified")

    print(f"\n📊 Market Memory Strength: {result.get('market_memory_strength', 'N/A')}")
    print(f"📈 Bias: {result.get('bias', 'N/A')}")

    if result.get("analysis"):
        print(f"\n📝 Analysis:\n{result['analysis']}")

    if result.get("current_relevance"):
        print(f"\n🎯 Current Relevance:\n{result['current_relevance']}")

    print("=" * 70)


def compare_structures(
    ai_structures: Dict[str, Any],
    user_structures: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Compare AI-identified structures with user-defined structures.
    Useful for training/feedback loop.
    """
    comparison = {
        "volume_nodes": {
            "ai": ai_structures.get("volume_nodes", []),
            "user": user_structures.get("volume_nodes", []),
            "agreement": [],
            "ai_only": [],
            "user_only": [],
        },
        "volume_wells": {
            "ai": ai_structures.get("volume_wells", []),
            "user": user_structures.get("volume_wells", []),
            "agreement": [],
            "ai_only": [],
            "user_only": [],
        },
        "crevasses": {
            "ai": ai_structures.get("crevasses", []),
            "user": user_structures.get("crevasses", []),
            "overlap_count": 0,
        },
    }

    # Compare nodes (within $10 tolerance)
    tolerance = 10
    ai_nodes = set(ai_structures.get("volume_nodes", []))
    user_nodes = set(user_structures.get("volume_nodes", []))

    for ai_node in ai_nodes:
        matched = False
        for user_node in user_nodes:
            if abs(ai_node - user_node) <= tolerance:
                comparison["volume_nodes"]["agreement"].append((ai_node, user_node))
                matched = True
                break
        if not matched:
            comparison["volume_nodes"]["ai_only"].append(ai_node)

    for user_node in user_nodes:
        matched = any(abs(user_node - ai_node) <= tolerance for ai_node in ai_nodes)
        if not matched:
            comparison["volume_nodes"]["user_only"].append(user_node)

    # Compare wells
    ai_wells = set(ai_structures.get("volume_wells", []))
    user_wells = set(user_structures.get("volume_wells", []))

    for ai_well in ai_wells:
        matched = False
        for user_well in user_wells:
            if abs(ai_well - user_well) <= tolerance:
                comparison["volume_wells"]["agreement"].append((ai_well, user_well))
                matched = True
                break
        if not matched:
            comparison["volume_wells"]["ai_only"].append(ai_well)

    for user_well in user_wells:
        matched = any(abs(user_well - ai_well) <= tolerance for ai_well in ai_wells)
        if not matched:
            comparison["volume_wells"]["user_only"].append(user_well)

    return comparison


def print_comparison(comparison: Dict[str, Any]) -> None:
    """Print structure comparison results."""
    print("\n" + "=" * 70)
    print("AI vs USER STRUCTURE COMPARISON")
    print("=" * 70)

    # Nodes
    nodes = comparison["volume_nodes"]
    print("\n📍 VOLUME NODES:")
    print(f"   Agreement ({len(nodes['agreement'])}):")
    for ai, user in nodes["agreement"]:
        print(f"      AI: ${ai:,} ≈ User: ${user:,}")

    if nodes["ai_only"]:
        print(f"   AI only ({len(nodes['ai_only'])}):")
        for p in nodes["ai_only"]:
            print(f"      ${p:,}")

    if nodes["user_only"]:
        print(f"   User only ({len(nodes['user_only'])}):")
        for p in nodes["user_only"]:
            print(f"      ${p:,}")

    # Wells
    wells = comparison["volume_wells"]
    print("\n📍 VOLUME WELLS:")
    print(f"   Agreement ({len(wells['agreement'])}):")
    for ai, user in wells["agreement"]:
        print(f"      AI: ${ai:,} ≈ User: ${user:,}")

    if wells["ai_only"]:
        print(f"   AI only ({len(wells['ai_only'])}):")
        for p in wells["ai_only"]:
            print(f"      ${p:,}")

    if wells["user_only"]:
        print(f"   User only ({len(wells['user_only'])}):")
        for p in wells["user_only"]:
            print(f"      ${p:,}")

    # Summary
    total_agreement = len(nodes["agreement"]) + len(wells["agreement"])
    total_ai = len(nodes["ai"]) + len(wells["ai"])
    total_user = len(nodes["user"]) + len(wells["user"])

    print(f"\n📊 SUMMARY:")
    print(f"   AI identified: {total_ai} structures")
    print(f"   User defined: {total_user} structures")
    print(f"   Agreement: {total_agreement} structures")

    if total_user > 0:
        accuracy = total_agreement / total_user * 100
        print(f"   Accuracy vs User: {accuracy:.1f}%")

    print("=" * 70)


# CLI interface
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AI Volume Profile Analysis")
    parser.add_argument("--image", required=True, help="Path to volume profile chart image")
    parser.add_argument("--model", default="claude-sonnet-4-20250514", help="Claude model to use")
    parser.add_argument("--compare", help="JSON file with user structures to compare")
    args = parser.parse_args()

    # Run analysis
    result = analyze_chart_with_claude(args.image, model=args.model)

    if result:
        print_ai_analysis(result)

        # Compare if user structures provided
        if args.compare and Path(args.compare).exists():
            with open(args.compare) as f:
                user_structures = json.load(f)
            comparison = compare_structures(result, user_structures)
            print_comparison(comparison)

        # Save result
        output_path = Path(args.image).with_suffix(".analysis.json")
        with open(output_path, "w") as f:
            json.dump(result, f, indent=2)
        log("ai", "💾", f"Saved analysis to {output_path}")
