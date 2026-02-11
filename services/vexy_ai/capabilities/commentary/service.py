"""
Commentary Service - Business logic for Vexy Play-by-Play commentary.

Handles:
- Epoch-based scheduled commentary
- Event-driven market commentary
- Intel article processing
- Publishing to market-redis
"""

import asyncio
import os
import time
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional, Set

from ...core.events import CommentaryGenerated, MarketEventDetected


class CommentaryService:
    """
    Vexy Play-by-Play commentary service.

    Runs as a background task that:
    - Monitors epoch schedules
    - Detects market events
    - Synthesizes and publishes commentary
    """

    def __init__(self, config: Dict[str, Any], logger: Any, buses: Any = None, market_intel=None):
        self.config = config
        self.logger = logger
        self.buses = buses
        self.market_intel = market_intel

        # State tracking
        self.last_epoch_name: Optional[str] = None
        self.last_event_ids: Set[str] = set()
        self.running = False

        # Daily counters
        self.current_day: Optional[str] = None
        self.daily_article_count = 0

        # Readers and synthesizer (lazy-loaded)
        self._market_reader = None
        self._article_reader = None
        self._synthesizer = None

    def _get_redis_clients(self):
        """Get sync Redis clients for internal operations."""
        # Always use sync Redis for commentary internals
        # (MarketReader, ArticleReader, etc. expect sync clients)
        # Use explicit import to avoid namespace pollution from redis.asyncio
        from redis import Redis as SyncRedis

        buses = self.config.get("buses", {}) or {}

        system_url = buses.get("system-redis", {}).get("url", "redis://127.0.0.1:6379")
        market_url = buses.get("market-redis", {}).get("url", "redis://127.0.0.1:6380")
        intel_url = buses.get("intel-redis", {}).get("url", "redis://127.0.0.1:6381")

        r_system = SyncRedis.from_url(system_url, decode_responses=True)
        r_market = SyncRedis.from_url(market_url, decode_responses=True)
        r_intel = SyncRedis.from_url(intel_url, decode_responses=True)

        return r_system, r_market, r_intel

    def _get_market_reader(self, r_market):
        """Lazy-load market reader."""
        if self._market_reader is None:
            from services.vexy_ai.intel.market_reader import MarketReader
            self._market_reader = MarketReader(r_market, self.logger)
        return self._market_reader

    def _get_article_reader(self, r_intel):
        """Lazy-load article reader."""
        if self._article_reader is None:
            from services.vexy_ai.intel.article_reader import ArticleReader
            self._article_reader = ArticleReader(r_intel, self.logger)
        return self._article_reader

    def _get_synthesizer(self):
        """Lazy-load synthesizer."""
        if self._synthesizer is None:
            from services.vexy_ai.intel.synthesizer import Synthesizer
            self._synthesizer = Synthesizer(self.config, self.logger)
        return self._synthesizer

    def _flag(self, r_system, name: str, default: int = 1) -> int:
        """Get stage switch value from Redis or env."""
        redis_key = f"pipeline:switch:{name}"
        try:
            val = r_system.get(redis_key)
            # Handle async Redis client returning coroutine
            if asyncio.iscoroutine(val):
                self.logger.warn(f"Async Redis detected for {redis_key}, falling back to env")
                val = None
            if val is not None:
                return int(val)
        except (ValueError, TypeError, Exception) as e:
            self.logger.debug(f"Redis flag check failed for {name}: {e}")

        env_val = os.getenv(f"VEXY_{name.upper()}", str(default))
        return 1 if env_val == "1" else (default if env_val is None else 0)

    async def run_loop(self) -> None:
        """
        Main commentary loop.

        Runs continuously, checking epochs and events on each cycle.
        """
        from services.vexy_ai.intel.epochs import should_speak_epoch, generate_epoch_commentary
        from services.vexy_ai.intel.events import get_triggered_events
        from services.vexy_ai.intel.publisher import publish, init as init_publisher
        from services.vexy_ai.intel.intel_feed import process_intel_articles
        from services.vexy_ai.intel.schedule import (
            is_trading_day,
            get_epochs_for_day,
            get_current_et,
        )

        self.running = True
        self.logger.info("Commentary loop starting", emoji="🎙️")

        r_system, r_market, r_intel = self._get_redis_clients()

        # Initialize publisher
        buses = self.config.get("buses", {}) or {}
        market_url = buses.get("market-redis", {}).get("url", "redis://127.0.0.1:6380")
        init_publisher(market_url)

        # Get readers and synthesizer
        market_reader = self._get_market_reader(r_market)
        article_reader = self._get_article_reader(r_intel)
        synthesizer = self._get_synthesizer()

        # Stage switches
        ENABLE_EPOCHS = self._flag(r_system, "epochs", 1)
        ENABLE_EVENTS = self._flag(r_system, "events", 1)
        ENABLE_INTEL = self._flag(r_system, "intel", 1)

        vexy_mode = os.getenv("VEXY_MODE", "full").lower()
        loop_sleep_sec = float(self.config.get("env", {}).get("VEXY_LOOP_SLEEP_SEC", "60"))

        self.logger.info(
            f"Epochs={'YES' if ENABLE_EPOCHS else 'NO'}, "
            f"Events={'YES' if ENABLE_EVENTS else 'NO'}, "
            f"Intel={'YES' if ENABLE_INTEL else 'NO'}",
            emoji="⚙️"
        )

        try:
            while self.running:
                cycle_start = time.time()
                now_et = get_current_et()
                current_time = now_et.strftime("%H:%M")
                today_str = now_et.strftime("%Y-%m-%d")

                # Reset daily counters on new day
                if self.current_day != today_str:
                    self.current_day = today_str
                    self.daily_article_count = 0
                    self.last_epoch_name = None

                trading_day = is_trading_day(self.config, now_et)
                epochs = get_epochs_for_day(self.config, now_et)

                # Epochs
                force_epoch = os.getenv("FORCE_EPOCH", "false").lower() == "true"
                if ENABLE_EPOCHS and vexy_mode in ["full", "epochs_only"] and (epochs or force_epoch):
                    epoch = should_speak_epoch(current_time, epochs)
                    if epoch and epoch["name"] != self.last_epoch_name:
                        await self._process_epoch(
                            epoch, trading_day, market_reader, article_reader, synthesizer, publish
                        )

                # Events (trading days only)
                if ENABLE_EVENTS and vexy_mode in ["full", "events_only"] and trading_day:
                    events = get_triggered_events(r_market)
                    for event in events:
                        eid = f"{event['type']}:{event.get('id', '')}"
                        if eid not in self.last_event_ids:
                            publish("event", event["commentary"], event)
                            self.last_event_ids.add(eid)
                            if len(self.last_event_ids) > 100:
                                self.last_event_ids = set(list(self.last_event_ids)[-50:])
                            self.logger.info(f"Event: {event['commentary'][:80]}...", emoji="💥")

                # Intel articles
                if ENABLE_INTEL and vexy_mode in ["full", "intel_only"] and trading_day:
                    processed = process_intel_articles(r_system, lambda s, e, m: None)
                    if processed:
                        self.logger.info(f"Published {processed} intel update(s)", emoji="📰")

                cycle_time = time.time() - cycle_start
                self.logger.debug(f"Cycle complete in {cycle_time:.1f}s")

                await asyncio.sleep(loop_sleep_sec)

        except asyncio.CancelledError:
            self.logger.info("Commentary loop cancelled", emoji="🛑")
            raise
        except Exception as e:
            self.logger.error(f"Commentary loop error: {e}", emoji="❌")
            raise
        finally:
            self.running = False
            self.logger.info("Commentary loop stopped", emoji="✓")

    async def _process_epoch(
        self,
        epoch: Dict[str, Any],
        trading_day: bool,
        market_reader,
        article_reader,
        synthesizer,
        publish,
    ) -> None:
        """Process a single epoch."""
        from services.vexy_ai.intel.epochs import generate_epoch_commentary

        epoch_type = epoch.get("type", "standard")
        prompt_focus = epoch.get("prompt_focus", "")

        if not trading_day and epoch_type == "digest":
            # Weekend/holiday digest
            digest_config = self.config.get("non_trading_days", {}).get("weekend_digest", {})
            lookback = digest_config.get("lookback_hours", 48)
            max_stories = digest_config.get("max_stories", 5)

            recent_articles = article_reader.get_recent_articles(
                max_count=max_stories * 2,
                max_age_hours=lookback,
            )

            commentary = synthesizer.synthesize_weekend_digest(
                recent_articles,
                epoch_name=epoch["name"],
                focus=prompt_focus,
            )

            if commentary:
                publish("epoch", commentary, {
                    "epoch": epoch["name"],
                    "voice": epoch.get("voice", "Observer"),
                    "type": "digest",
                    "articles_used": len(recent_articles),
                })
                self.last_epoch_name = epoch["name"]
                self.logger.info(f"[Digest] {commentary[:80]}...", emoji="🎙️")
        else:
            # Trading day epoch — prefer market_intel for raw state
            if self.market_intel:
                market_state = self.market_intel.get_raw_state()
                # Enrich with SoM lenses (additive, existing keys preserved)
                try:
                    som = self.market_intel.get_som()
                    market_state["som_lenses"] = {
                        "vix_regime": (som.get("big_picture_volatility") or {}).get("regime_key"),
                        "event_posture": (som.get("event_energy") or {}).get("event_posture"),
                        "temperature": (som.get("convexity_temperature") or {}).get("temperature"),
                    }
                except Exception:
                    pass
            else:
                market_state = market_reader.get_market_state()
            recent_articles = article_reader.get_recent_articles(max_count=8, max_age_hours=6)
            articles_text = article_reader.format_for_prompt(recent_articles)

            commentary = synthesizer.synthesize(epoch, market_state, articles_text)
            if not commentary:
                commentary = generate_epoch_commentary(epoch, market_state)

            publish("epoch", commentary, {
                "epoch": epoch["name"],
                "voice": epoch.get("voice", "Observer"),
                "partitions": epoch.get("partitions", []),
                "reflection_dial": epoch.get("reflection_dial", 0.4),
                "market_state": market_state,
                "articles_used": len(recent_articles),
            })
            self.last_epoch_name = epoch["name"]
            self.logger.info(f"[{epoch.get('voice', 'Observer')}] {commentary[:80]}...", emoji="🎙️")

    def stop(self) -> None:
        """Signal the loop to stop."""
        self.running = False

    def get_status(self) -> Dict[str, Any]:
        """Get current commentary status."""
        from services.vexy_ai.intel.schedule import is_trading_day, get_current_et

        now_et = get_current_et()
        trading_day = is_trading_day(self.config, now_et)

        return {
            "running": self.running,
            "last_epoch": self.last_epoch_name,
            "schedule_type": "trading" if trading_day else "non-trading",
            "current_day": self.current_day,
        }

    def get_today_messages(self) -> List[Dict[str, Any]]:
        """Get all messages published today."""
        from services.vexy_ai.intel.publisher import get_today_messages
        return get_today_messages()
