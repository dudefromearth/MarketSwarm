"""
EconomicIndicatorRegistry — DB-backed lookup for economic indicators.

On startup: queries MySQL, builds in-memory key index + alias index.
Subscribes to Redis pub/sub channel for live cache invalidation.
"""

from __future__ import annotations

import os
import threading
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, unquote


class EconomicIndicatorRegistry:
    """
    In-memory registry of economic indicators backed by MySQL.

    Provides fast O(1) lookups by key or case-insensitive alias.
    Cache is refreshed via Redis pub/sub when admin CRUD mutations occur.
    """

    # Rating → impact label mapping (matches plan tier logic)
    _IMPACT_LABELS = {
        range(9, 11): "Very High",  # 9-10
        range(7, 9): "High",        # 7-8
        range(5, 7): "Medium",      # 5-6
        range(1, 5): "Low",         # 1-4
    }

    def __init__(self, config: Dict[str, Any], logger: Any):
        self._config = config
        self._logger = logger
        self._key_index: Dict[str, Dict[str, Any]] = {}
        self._alias_index: Dict[str, Dict[str, Any]] = {}
        self._loaded = False
        self._sub_thread: Optional[threading.Thread] = None

    # ── Public API ──────────────────────────────────────────────────

    def load_from_db(self) -> None:
        """Query DB and build both indexes. Called on startup."""
        conn = self._get_connection()
        if not conn:
            self._logger.warning("No DB connection — indicator registry empty", emoji="⚠️")
            return

        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, `key`, name, rating, tier, description "
                    "FROM economic_indicators WHERE is_active = 1"
                )
                indicators = cur.fetchall()

                cur.execute(
                    "SELECT indicator_id, alias FROM economic_indicator_aliases"
                )
                aliases = cur.fetchall()
        finally:
            conn.close()

        # Build alias map grouped by indicator_id
        alias_map: Dict[str, List[str]] = {}
        for row in aliases:
            iid = row["indicator_id"]
            if iid not in alias_map:
                alias_map[iid] = []
            alias_map[iid].append(row["alias"])

        # Build indexes
        key_index: Dict[str, Dict[str, Any]] = {}
        alias_index: Dict[str, Dict[str, Any]] = {}

        for ind in indicators:
            entry = {
                "id": ind["id"],
                "key": ind["key"],
                "name": ind["name"],
                "rating": ind["rating"],
                "tier": ind["tier"],
                "description": ind["description"],
                "aliases": alias_map.get(ind["id"], []),
            }
            key_index[ind["key"]] = entry

            # Index all aliases (case-insensitive)
            for alias in entry["aliases"]:
                alias_index[alias.lower()] = entry
            # Also index the name itself
            alias_index[ind["name"].lower()] = entry

        self._key_index = key_index
        self._alias_index = alias_index
        self._loaded = True
        self._logger.info(
            f"Loaded {len(key_index)} economic indicators, "
            f"{len(alias_index)} alias entries",
            emoji="📊"
        )

    def get_by_key(self, key: str) -> Optional[Dict[str, Any]]:
        """Direct key lookup."""
        return self._key_index.get(key)

    def get_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Reverse alias lookup (case-insensitive)."""
        return self._alias_index.get(name.lower())

    def get_rating(self, name: str) -> int:
        """Returns rating for an event name, or 3 (default/low) for unknowns."""
        entry = self.get_by_name(name)
        if entry:
            return entry["rating"]
        return 3

    def get_impact_label(self, rating: int) -> str:
        """Map numeric rating to impact label string."""
        for r_range, label in self._IMPACT_LABELS.items():
            if rating in r_range:
                return label
        return "Low"

    def refresh_cache(self) -> None:
        """Re-query DB and rebuild indexes."""
        self._logger.info("Refreshing economic indicator cache...", emoji="🔄")
        self.load_from_db()

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def count(self) -> int:
        return len(self._key_index)

    # ── Redis Pub/Sub Subscription ──────────────────────────────────

    def start_subscription(self) -> None:
        """Subscribe to Redis channel for live cache invalidation (background thread)."""
        self._sub_thread = threading.Thread(
            target=self._subscribe_loop,
            daemon=True,
            name="econ-indicator-sub",
        )
        self._sub_thread.start()

    def _subscribe_loop(self) -> None:
        """Background thread: listen for refresh messages on Redis pub/sub."""
        try:
            import redis as redis_lib

            buses = self._config.get("buses", {}) or {}
            market_url = buses.get("market-redis", {}).get("url", "redis://127.0.0.1:6380")
            r = redis_lib.from_url(market_url, decode_responses=True)
            ps = r.pubsub()
            ps.subscribe("vexy:econ-indicators:refresh")
            self._logger.info(
                "Subscribed to vexy:econ-indicators:refresh channel",
                emoji="📡"
            )

            for message in ps.listen():
                if message["type"] == "message":
                    self._logger.info(
                        "Received indicator refresh signal",
                        emoji="🔄"
                    )
                    try:
                        self.refresh_cache()
                    except Exception as e:
                        self._logger.error(
                            f"Failed to refresh indicator cache: {e}",
                            emoji="❌"
                        )
        except Exception as e:
            self._logger.error(
                f"Indicator subscription thread failed: {e}",
                emoji="❌"
            )

    # ── Private ─────────────────────────────────────────────────────

    def _get_connection(self):
        """Get a pymysql connection from the DB URL."""
        db_url = self._resolve_db_url()
        if not db_url:
            return None

        try:
            import pymysql
            import pymysql.cursors

            parsed = urlparse(db_url.replace("mysql+pymysql://", "mysql://"))
            conn = pymysql.connect(
                host=parsed.hostname or "127.0.0.1",
                port=parsed.port or 3306,
                user=parsed.username or "root",
                password=unquote(parsed.password or ""),
                database=parsed.path.lstrip("/"),
                cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=5,
            )
            return conn
        except Exception as e:
            self._logger.error(f"DB connection failed: {e}", emoji="❌")
            return None

    def _resolve_db_url(self) -> Optional[str]:
        """Resolve DATABASE_URL from env or config."""
        # Try env var first
        url = os.getenv("DATABASE_URL")
        if url:
            return url

        # Try config (if SSE shares truth with vexy)
        url = self._config.get("DATABASE_URL")
        if url:
            return url

        # Fallback to default
        return "mysql://fotw_app:PfedKtaTaAa2iV21QTZp@127.0.0.1:3306/fotw_app"
