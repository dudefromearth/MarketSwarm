# strategy.py
"""
Feed Transformation Strategies for RSS Aggregator
------------------------------------------------
Normalizes raw ingested RSS article items into a canonical,
uniform schema for publishing and downstream processing.

Strategies:
 - MinimalFeedStrategy (Google-style minimal RSS)
 - StandardFeedStrategy (RSS/Atom summary/description style)

Auto-detected via detect_strategy().
"""

from typing import Dict, Any


# ------------------------------------------------------------
# Base Strategy Interface
# ------------------------------------------------------------

class FeedStrategy:
    """Base class for feed transformation strategies."""

    def transform(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize an RSS item into canonical form:

        {
            "title": str,
            "url": str,
            "abstract": str,
            "published": str,
            "image": str,
        }
        """
        raise NotImplementedError("Strategy must implement transform()")


# ------------------------------------------------------------
# MinimalFeedStrategy — Google-style minimal feeds
# ------------------------------------------------------------

class MinimalFeedStrategy(FeedStrategy):
    """Strategy for minimal feeds: title + link + optional abstract."""

    def transform(self, item: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "title": item.get("title", "Untitled"),
            "url": item.get("url") or item.get("link", ""),
            "abstract": item.get("abstract") or "",
            "published": item.get("published") or item.get("timestamp", ""),
            "image": item.get("image") or "",
        }


# ------------------------------------------------------------
# StandardFeedStrategy — RSS/Atom conventional feeds
# ------------------------------------------------------------

class StandardFeedStrategy(FeedStrategy):
    """Strategy for feeds that include summary/description."""

    def transform(self, item: Dict[str, Any]) -> Dict[str, Any]:
        abstract = (
            item.get("summary")
            or item.get("description")
            or item.get("abstract")
            or ""
        )

        return {
            "title": item.get("title", "Untitled"),
            "url": item.get("url") or item.get("link", ""),
            "abstract": abstract,
            "published": item.get("published") or item.get("timestamp", ""),
            "image": item.get("image") or "",
        }


# ------------------------------------------------------------
# Strategy Detection
# ------------------------------------------------------------

def detect_strategy(item: Dict[str, Any]) -> FeedStrategy:
    """
    Inspect available fields and choose the most appropriate strategy.
    """

    # Rich RSS/Atom feed → use Standard strategy
    if "summary" in item or "description" in item:
        return StandardFeedStrategy()

    # Google-style minimal feed → use Minimal strategy
    if "abstract" in item:
        return MinimalFeedStrategy()

    # Fallback-safe
    return MinimalFeedStrategy()


# ------------------------------------------------------------
# Convenience Wrapper
# ------------------------------------------------------------

def normalize_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize the feed item using the detected strategy.
    """
    strategy = detect_strategy(item)
    return strategy.transform(item)