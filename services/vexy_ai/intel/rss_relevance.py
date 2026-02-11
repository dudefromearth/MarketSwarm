"""
RSSRelevanceEngine — Scores enriched RSS articles for SoM relevance.

Reads from intel-redis (rss:article_enriched_index + hashes).
Writes top results to market-redis (som:unscheduled_developments).
Called every 60s by the routine capability background task.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from typing import Any, Dict, List

import pytz

# ── Category → Market Relevance base score ────────────────────────────

_CATEGORY_RELEVANCE: Dict[str, int] = {
    "geopolitics": 5,
    "macro": 5,
    "rates": 4,
    "politics": 4,
    "energy": 3,
    "commodities": 3,
    "equities": 2,
}
_DEFAULT_RELEVANCE = 1

# Entities that boost relevance by +1
_RELEVANCE_BOOST_ENTITIES = {"Fed", "FOMC", "Treasury", "VIX", "SPX"}

# ── Shock keywords ────────────────────────────────────────────────────

_SHOCK_KEYWORDS = {"military", "war", "sanctions", "attack", "nuclear"}

# ── Structural categories ─────────────────────────────────────────────

_STRUCTURAL_CATEGORIES = {"macro", "rates", "treasury_liquidity"}
_STRUCTURAL_ENTITIES = {"Fed", "FOMC", "Treasury"}

# ── Forbidden tokens for headline/summary cleanup ─────────────────────

_FORBIDDEN_TOKENS = [
    "expect", "likely", "should", "watch",
    "traders may", "markets poised", "analysts say",
    "enter", "exit", "avoid", "take profit", "stop loss",
]

_FORBIDDEN_RE = re.compile(
    r'\b(' + '|'.join(re.escape(t) for t in _FORBIDDEN_TOKENS) + r')\b',
    re.IGNORECASE,
)


class RSSRelevanceEngine:
    """Deterministic scorer for RSS articles → SoM unscheduled developments."""

    def __init__(self, r_intel, r_market, logger):
        self._r_intel = r_intel
        self._r_market = r_market
        self._logger = logger

    def score_and_cache(self) -> None:
        """Score recent enriched articles and cache top results."""
        try:
            articles = self._read_recent_articles()
            scored = self._score_articles(articles)
            filtered = self._filter_and_dedupe(scored)
            self._write_cache(filtered[:2])  # Max 2 results
        except Exception as e:
            self._logger.warning(f"RSS relevance scoring failed: {e}", emoji="⚠️")

    # ── Read from intel-redis ─────────────────────────────────────

    def _read_recent_articles(self) -> List[Dict[str, Any]]:
        """Read enriched articles from last 4 hours."""
        cutoff = time.time() - (4 * 3600)

        # Get UIDs from ZSET, newest first
        uids = self._r_intel.zrevrangebyscore(
            "rss:article_enriched_index",
            "+inf",
            cutoff,
            start=0,
            num=100,
        )

        articles = []
        for uid in uids:
            data = self._r_intel.hgetall(f"rss:article_enriched:{uid}")
            if not data:
                continue

            # Basic filters: quality_score ≥ 0.5, has summary
            quality = float(data.get("quality_score", 0))
            if quality < 0.5:
                continue
            if not data.get("summary"):
                continue

            # Parse JSON fields
            entities = []
            try:
                entities = json.loads(data.get("entities", "[]"))
            except (json.JSONDecodeError, TypeError):
                pass

            tickers = []
            try:
                tickers = json.loads(data.get("tickers", "[]"))
            except (json.JSONDecodeError, TypeError):
                pass

            articles.append({
                "uid": uid,
                "title": data.get("title", ""),
                "summary": data.get("summary", ""),
                "category": data.get("category", "").lower(),
                "quality_score": quality,
                "entities": entities,
                "tickers": tickers,
                "enriched_ts": float(data.get("enriched_ts", 0)),
            })

        return articles

    # ── Scoring ───────────────────────────────────────────────────

    def _score_articles(self, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Score each article for relevance, urgency, and impact."""
        now = time.time()
        scored = []

        for art in articles:
            relevance = self._score_relevance(art)
            urgency = self._score_urgency(art, now)
            impact = self._classify_impact(art, relevance)

            art["relevance"] = relevance
            art["urgency"] = urgency
            art["impact"] = impact
            art["total_score"] = relevance + urgency
            scored.append(art)

        scored.sort(key=lambda a: a["total_score"], reverse=True)
        return scored

    def _score_relevance(self, art: Dict[str, Any]) -> int:
        """Market Relevance: 0–5 based on category + entity boost."""
        category = art.get("category", "")
        base = _CATEGORY_RELEVANCE.get(category, _DEFAULT_RELEVANCE)

        entities_set = set(art.get("entities", []))
        if entities_set & _RELEVANCE_BOOST_ENTITIES:
            base += 1

        return min(base, 5)

    def _score_urgency(self, art: Dict[str, Any], now: float) -> int:
        """Urgency: 0–5 based on age + category boost."""
        age_minutes = (now - art.get("enriched_ts", now)) / 60

        if age_minutes < 30:
            score = 5
        elif age_minutes < 60:
            score = 4
        elif age_minutes < 120:
            score = 3
        elif age_minutes < 180:
            score = 2
        elif age_minutes < 240:
            score = 1
        else:
            score = 0

        category = art.get("category", "")
        if category in ("geopolitics", "macro"):
            score += 1

        return min(score, 5)

    def _classify_impact(self, art: Dict[str, Any], relevance: int) -> str:
        """Convexity Impact classification."""
        category = art.get("category", "")
        entities_set = set(art.get("entities", []))
        text_lower = (art.get("title", "") + " " + art.get("summary", "")).lower()

        # Shock: geopolitics + shock keywords
        if category == "geopolitics":
            if any(kw in text_lower for kw in _SHOCK_KEYWORDS):
                return "shock"

        # Structural: macro/rates/treasury_liquidity OR key entities
        if category in _STRUCTURAL_CATEGORIES:
            return "structural"
        if entities_set & _STRUCTURAL_ENTITIES:
            return "structural"

        # Mild: politics, energy, commodities with relevance ≥ 3
        if category in ("politics", "energy", "commodities") and relevance >= 3:
            return "mild"

        return "none"

    # ── Filtering & Deduplication ─────────────────────────────────

    def _filter_and_dedupe(self, scored: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Apply filtering rules and deduplicate."""
        today_events = self._get_today_event_names()

        candidates = []
        for art in scored:
            # Relevance gate
            if art["relevance"] < 4:
                continue

            # Commentary heuristic
            if art["quality_score"] < 0.3:
                continue

            # Impact must not be "none"
            if art["impact"] == "none":
                continue

            # Skip if title overlaps with scheduled events
            title_lower = art["title"].lower()
            if any(evt_name.lower() in title_lower for evt_name in today_events):
                continue

            candidates.append(art)

        # Deduplicate by entity overlap (≥ 2 shared entities → keep higher-scored)
        deduped = []
        for art in candidates:
            art_entities = set(art.get("entities", []))
            is_dupe = False
            for existing in deduped:
                existing_entities = set(existing.get("entities", []))
                if len(art_entities & existing_entities) >= 2:
                    is_dupe = True
                    break
            if not is_dupe:
                deduped.append(art)

        return deduped

    def _get_today_event_names(self) -> List[str]:
        """Get today's ECONOMIC_CALENDAR event names."""
        from services.vexy_ai.market_state import ECONOMIC_CALENDAR

        et = pytz.timezone("America/New_York")
        today_str = datetime.now(et).strftime("%Y-%m-%d")
        events = ECONOMIC_CALENDAR.get(today_str, [])
        return [e["name"] for e in events]

    # ── Output ────────────────────────────────────────────────────

    def _write_cache(self, results: List[Dict[str, Any]]) -> None:
        """Write results to market-redis with 300s TTL."""
        output = []
        for art in results:
            headline = self._clean_text(art.get("title", ""))
            summary = self._extract_first_sentence(art.get("summary", ""))
            summary = self._clean_text(summary)

            output.append({
                "headline": headline,
                "summary": summary,
                "impact": art["impact"],
            })

        self._r_market.set(
            "som:unscheduled_developments",
            json.dumps(output),
            ex=300,
        )

        if output:
            self._logger.info(
                f"RSS relevance: cached {len(output)} unscheduled development(s)",
                emoji="📡",
            )

    def _clean_text(self, text: str) -> str:
        """Strip forbidden tokens from text."""
        cleaned = _FORBIDDEN_RE.sub("", text)
        return re.sub(r'\s+', ' ', cleaned).strip()

    def _extract_first_sentence(self, text: str) -> str:
        """Extract first sentence from summary."""
        match = re.match(r'^(.+?[.!?])(?:\s|$)', text)
        if match:
            return match.group(1)
        return text[:200]
