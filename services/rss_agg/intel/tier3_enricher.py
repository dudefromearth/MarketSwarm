#!/usr/bin/env python3
"""
Tier-3 Enricher (Markdown Baseline)
-----------------------------------
Input:
    - raw_text: canonical MARKDOWN
    - title: canonical extracted title
    - fallback_image: canonical first-img

Output:
    - JSON metadata with full provenance
    - Never crashes — even on empty/malformed LLM responses
"""

import os
import re
import json
import time
from datetime import datetime
from openai import OpenAI

# ------------------------------------------------------------
# LLM Client (lazy initialization)
# ------------------------------------------------------------
_client = None
_config = {}


def init_from_config(config):
    """Store config for later client initialization."""
    global _config
    _config = config


def get_client():
    """Get OpenAI client, initializing lazily on first use."""
    global _client
    if _client is None:
        env = _config.get("env", {}) or {}
        api_key = (
            _config.get("OPENAI_API_KEY") or
            env.get("OPENAI_API_KEY") or
            os.getenv("OPENAI_API_KEY") or
            ""
        )
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not found in config or environment")
        _client = OpenAI(api_key=api_key)
    return _client

# ------------------------------------------------------------
# Logging helper
# ------------------------------------------------------------
def log(status: str, emoji: str, msg: str):
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [tier3] [{status}] {emoji} {msg}")

# ------------------------------------------------------------
# Prompt (strict JSON output)
# ------------------------------------------------------------
TIER3_PROMPT = """
You are an expert financial editor and analyst.

You will receive:
- an article TITLE
- the full article content in MARKDOWN format
- optional fallback image URL

Your job is to output a **pure JSON object** with exactly these keys:

{
  "clean_title": "...",
  "abstract": "...",
  "summary": "...",
  "takeaways": [...],
  "sentiment": "Bullish|Bearish|Neutral",
  "entities": [...],
  "tickers": [...],
  "category": "macro|equities|fx|rates|crypto|earnings|energy|commodities|politics|geopolitics|misc",
  "quality_score": 0.0-1.0,
  "reading_time": integer,
  "hero_image": "url or empty string"
}

Return ONLY the JSON. No markdown. No explanation. No refusal.
"""

# ------------------------------------------------------------
# Robust JSON extractor (never fails)
# ------------------------------------------------------------
def extract_json_from_string(text: str) -> dict:
    text = text.strip()
    if not text:
        return {}

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Find first { ... } or [ ... ]
    match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    log("warn", "JSON", "Could not extract valid JSON from LLM response")
    return {}

# ------------------------------------------------------------
# Fallback metadata (deterministic)
# ------------------------------------------------------------
def fallback_metadata(raw_text: str, title: str, fallback_image: str = "") -> dict:
    parts = [p.strip() for p in raw_text.split("\n") if p.strip()]
    abstract = parts[0] if parts else raw_text[:300].strip()
    summary = "\n\n".join(parts[:2]) if len(parts) >= 2 else raw_text[:500].strip()

    word_count = len(raw_text.split())
    reading_time = max(1, word_count // 200)

    return {
        "clean_title": title or "Untitled",
        "abstract": abstract,
        "summary": summary,
        "takeaways": [],
        "entities": [],
        "tickers": [],
        "sentiment": "Neutral",
        "category": "misc",
        "quality_score": 0.20,
        "reading_time": reading_time,
        "hero_image": fallback_image or "",
        "generated_ts": time.time(),
        "enrichment_source": "static-fallback",
        "enrichment_model": "static-v1",
        "enriched_at": datetime.utcnow().isoformat() + "Z"
    }

# ------------------------------------------------------------
# MAIN CALL — never crashes
# ------------------------------------------------------------
def generate_tier3_metadata(raw_text: str, title: str, fallback_image: str = "") -> dict:
    env = _config.get("env", {}) or {}
    LLM_MODE = (_config.get("LLM_MODE") or env.get("LLM_MODE") or os.getenv("LLM_MODE", "online")).lower()

    if LLM_MODE == "offline":
        log("info", "OFF", "LLM_MODE=offline → using static fallback")
        return fallback_metadata(raw_text, title, fallback_image)

    try:
        content = f"TITLE:\n{title}\n\nMARKDOWN ARTICLE CONTENT:\n{raw_text}\n\nFALLBACK IMAGE:\n{fallback_image}"

        model = _config.get("ENRICHMENT_MODEL") or env.get("ENRICHMENT_MODEL") or os.getenv("ENRICHMENT_MODEL", "gpt-4o")
        response = get_client().chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": TIER3_PROMPT},
                {"role": "user",   "content": content}
            ],
            temperature=0.0,
            max_tokens=1024,
            timeout=30
        )

        raw_output = response.choices[0].message.content.strip()
        log("debug", "RAW", f"LLM returned {len(raw_output)} chars")

        # Extract JSON safely
        data = extract_json_from_string(raw_output)

        # Validate required fields
        required = {"clean_title", "abstract", "summary"}
        if not data or not required.issubset(data.keys()):
            log("warn", "FALLBACK", "Invalid or incomplete JSON → using static fallback")
            return fallback_metadata(raw_text, title, fallback_image)

        # Apply hero_image fallback
        if fallback_image and not data.get("hero_image"):
            data["hero_image"] = fallback_image

        # Add provenance (success path)
        data["generated_ts"] = time.time()
        data["enrichment_source"] = "llm-success"
        data["enrichment_model"] = model
        data["enriched_at"] = datetime.utcnow().isoformat() + "Z"

        log("info", "SUCCESS", "LLM enrichment succeeded")
        return data

    except Exception as e:
        log("error", "FAIL", f"LLM call failed: {e}")
        return fallback_metadata(raw_text, title, fallback_image)