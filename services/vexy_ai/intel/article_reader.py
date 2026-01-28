#!/usr/bin/env python3
"""
article_reader.py — Read recent articles from RSS Agg (intel-redis)

Provides recent news context for Vexy AI epoch synthesis.
"""

from __future__ import annotations

import json
from datetime import datetime, UTC, timedelta
from typing import Any, Dict, List, Optional

import redis


class ArticleReader:
    """
    Reads enriched articles from RSS Agg in intel-redis.
    """

    def __init__(self, r_intel: redis.Redis, logger=None):
        self.r = r_intel
        self.logger = logger

    def _log(self, msg: str, emoji: str = "📰"):
        if self.logger:
            self.logger.info(msg, emoji=emoji)

    def get_recent_articles(self, max_count: int = 10, max_age_hours: int = 4) -> List[Dict[str, Any]]:
        """
        Get recent enriched articles from RSS Agg.

        Args:
            max_count: Maximum number of articles to return
            max_age_hours: Only include articles published within this many hours

        Returns:
            List of article dicts with summary, sentiment, takeaways, entities
        """
        articles = []
        cutoff = datetime.now(UTC) - timedelta(hours=max_age_hours)

        # Scan for enriched article keys
        cursor = 0
        keys = []
        while True:
            cursor, batch = self.r.scan(cursor, match="rss:article_enriched:*", count=100)
            keys.extend(batch)
            if cursor == 0:
                break

        self._log(f"found {len(keys)} enriched articles in intel-redis")

        # Fetch and filter articles
        for key in keys:
            try:
                data = self.r.hgetall(key)
                if not data:
                    continue

                # Parse published date if available
                published_str = data.get("published")
                if published_str:
                    try:
                        # Try ISO format first
                        published = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
                        if published < cutoff:
                            continue  # Skip old articles
                    except (ValueError, TypeError):
                        pass  # Keep article if we can't parse date

                # Extract relevant fields
                article = {
                    "uid": data.get("uid", ""),
                    "title": data.get("clean_text", data.get("title", "")).strip(),
                    "summary": data.get("summary", ""),
                    "sentiment": data.get("sentiment", "neutral"),
                    "takeaways": self._parse_list(data.get("takeaways", "[]")),
                    "entities": self._parse_list(data.get("entities", "[]")),
                    "published": published_str,
                }

                if article["summary"]:  # Only include articles with summaries
                    articles.append(article)

            except (redis.RedisError, json.JSONDecodeError) as e:
                self._log(f"error reading article {key}: {e}", emoji="⚠️")
                continue

        # Sort by published date (newest first) and limit
        articles.sort(key=lambda x: x.get("published", ""), reverse=True)
        articles = articles[:max_count]

        self._log(f"returning {len(articles)} recent articles for synthesis")
        return articles

    def _parse_list(self, raw: str) -> List[str]:
        """Parse a JSON list string, returning empty list on failure."""
        if not raw:
            return []
        try:
            result = json.loads(raw)
            return result if isinstance(result, list) else []
        except json.JSONDecodeError:
            return []

    def format_for_prompt(self, articles: List[Dict[str, Any]]) -> str:
        """
        Format articles for inclusion in LLM prompt.
        """
        if not articles:
            return "No recent news articles available."

        lines = ["Recent market news:"]
        for i, article in enumerate(articles, 1):
            title = article.get("title", "Untitled")
            summary = article.get("summary", "")
            sentiment = article.get("sentiment", "neutral")

            lines.append(f"\n{i}. {title}")
            if summary:
                lines.append(f"   {summary[:200]}...")
            lines.append(f"   Sentiment: {sentiment}")

        return "\n".join(lines)
