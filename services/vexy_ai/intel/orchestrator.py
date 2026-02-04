#!/usr/bin/env python3
"""
vexy_orchestrator.py — Vexy AI Play-by-Play Engine

Behavior:
  - Reads mode + stage switches from system-redis and env
  - Epoch commentary with market data from Massive + RSS Agg
  - Event commentary (events module)
  - Intel article commentary (intel_feed module)
  - Publishes via publisher.publish(...)
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, UTC
from typing import Any, Dict, Set

import redis

from .epochs import should_speak_epoch, generate_epoch_commentary
from .events import get_triggered_events
from .publisher import publish, init as init_publisher
from .intel_feed import process_intel_articles
from .market_reader import MarketReader
from .article_reader import ArticleReader
from .synthesizer import Synthesizer
from .schedule import (
    is_trading_day,
    is_market_hours,
    get_epochs_for_day,
    get_active_schedule,
    get_system_preferences,
    get_article_trigger_config,
    get_current_et,
)


# Vexy mode control
VEXY_MODE = os.getenv("VEXY_MODE", "full").lower()

# Emoji map for Vexy "voice" messages
EMOJI = {
    "startup": "🚀",
    "config": "⚙️",
    "epoch_check": "🔍",
    "epoch_speak": "🎙️",
    "event_check": "👀",
    "event_fire": "💥",
    "cycle": "⏰",
    "info": "📘",
    "warn": "⚠️",
    "ok": "✅",
    "fail": "❌",
}


def emit(step: str, emoji_key: str, msg: str) -> None:
    """
    Vexy "voice" output.
    """
    ts = datetime.now(UTC).strftime("%H:%M:%S")
    emoji = EMOJI.get(emoji_key, "📘")
    print(f"[{ts}][vexy_ai|{step}] {emoji} {msg}")


# Global state for de-duplication and context
last_epoch_name: str | None = None
last_event_ids: Set[str] = set()


def _flag(r_system: redis.Redis, name: str, default: int = 1) -> int:
    """
    Stage switches for Vexy.
    """
    redis_key = f"pipeline:switch:{name}"
    val = r_system.get(redis_key)
    if val is not None:
        try:
            return int(val)
        except ValueError:
            pass

    env_val = os.getenv(f"VEXY_{name.upper()}", str(default))
    return int(env_val == "1")


async def run(config: Dict[str, Any], logger) -> None:
    """
    Async orchestrator entrypoint for vexy_ai.
    """
    global last_epoch_name, last_event_ids

    service_name = config.get("service_name", "vexy_ai")

    # ------------------------------------------------------------
    # Redis connections from Truth / config
    # ------------------------------------------------------------
    buses = config.get("buses", {}) or {}
    system_url = (
        buses.get("system-redis", {}).get("url")
        or os.getenv("SYSTEM_REDIS_URL", "redis://127.0.0.1:6379")
    )
    market_url = (
        buses.get("market-redis", {}).get("url")
        or os.getenv("MARKET_REDIS_URL", "redis://127.0.0.1:6380")
    )
    intel_url = (
        buses.get("intel-redis", {}).get("url")
        or os.getenv("INTEL_REDIS_URL", "redis://127.0.0.1:6381")
    )

    r_system = redis.Redis.from_url(system_url, decode_responses=True)
    r_market = redis.Redis.from_url(market_url, decode_responses=True)
    r_intel = redis.Redis.from_url(intel_url, decode_responses=True)

    # Initialize publisher with correct market Redis URL
    init_publisher(market_url)

    # Market data reader (consumes Massive models)
    market_reader = MarketReader(r_market, logger)

    # Article reader (consumes RSS Agg articles)
    article_reader = ArticleReader(r_intel, logger)

    # LLM synthesizer for epoch commentary
    synthesizer = Synthesizer(config, logger)

    # Stage switches
    ENABLE_EPOCHS = _flag(r_system, "epochs", 1)
    ENABLE_EVENTS = _flag(r_system, "events", 1)
    ENABLE_INTEL = _flag(r_system, "intel", 1)

    # ------------------------------------------------------------
    # Startup logs
    # ------------------------------------------------------------
    logger.info("orchestrator starting", emoji="🚀")
    logger.info(f"VEXY_MODE={VEXY_MODE}", emoji="⚙️")
    logger.info(
        f"Epochs={'YES' if ENABLE_EPOCHS else 'NO'}, "
        f"Events={'YES' if ENABLE_EVENTS else 'NO'}, "
        f"Intel={'YES' if ENABLE_INTEL else 'NO'}",
        emoji="⚙️",
    )

    emit("startup", "startup", "Vexy AI Play-by-Play Engine starting")
    emit("config", "config", f"VEXY_MODE={VEXY_MODE}")

    env = config.get("env", {})
    loop_sleep_sec = float(env.get("VEXY_LOOP_SLEEP_SEC", "60"))

    # Article-driven state for non-trading days
    article_batch_start: float | None = None
    article_batch_count: int = 0
    last_article_publish: float = 0
    daily_article_count: int = 0
    current_day: str | None = None

    try:
        while True:
            cycle_start = time.time()
            now_et = get_current_et()
            now = datetime.now()
            current_time = now_et.strftime("%H:%M")
            today_str = now_et.strftime("%Y-%m-%d")

            # Reset daily counters on new day
            if current_day != today_str:
                current_day = today_str
                daily_article_count = 0
                last_epoch_name = None
                emit("system", "info", f"New day: {today_str}")

            # Determine schedule type
            trading_day = is_trading_day(config, now_et)
            schedule = get_active_schedule(config, now_et)
            epochs = get_epochs_for_day(config, now_et)

            schedule_type = "trading" if trading_day else "non-trading"
            emit("system", "info", f"Schedule: {schedule_type} | Epochs: {len(epochs)}")

            # -----------------------------
            # Epochs (with market data + news synthesis)
            # -----------------------------
            force_epoch = os.getenv("FORCE_EPOCH", "false").lower() == "true"
            if ENABLE_EPOCHS and VEXY_MODE in ["full", "epochs_only"] and (epochs or force_epoch):
                emit("epoch", "epoch_check", f"Checking {len(epochs)} epoch triggers… (force={force_epoch})")
                epoch = should_speak_epoch(current_time, epochs)
                if epoch and epoch["name"] != last_epoch_name:
                    epoch_type = epoch.get("type", "standard")
                    prompt_focus = epoch.get("prompt_focus", "")

                    # Non-trading day digest epochs
                    if not trading_day and epoch_type == "digest":
                        # Weekend/holiday digest - summarize top stories
                        digest_config = config.get("non_trading_days", {}).get("weekend_digest", {})
                        lookback = digest_config.get("lookback_hours", 48)
                        max_stories = digest_config.get("max_stories", 5)

                        recent_articles = article_reader.get_recent_articles(
                            max_count=max_stories * 2,  # Get extra for filtering
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
                                "schedule_type": schedule_type,
                            })
                            last_epoch_name = epoch["name"]
                            emit("epoch", "epoch_speak", f"[Digest] {commentary[:100]}…")
                        else:
                            emit("epoch", "warn", f"No stories for {epoch['name']} digest")

                    else:
                        # Trading day or standard epoch - use market data synthesis
                        market_state = market_reader.get_market_state()

                        # Fetch recent articles for synthesis
                        recent_articles = article_reader.get_recent_articles(max_count=8, max_age_hours=6)
                        articles_text = article_reader.format_for_prompt(recent_articles)

                        # Try LLM synthesis first, fall back to template
                        commentary = synthesizer.synthesize(epoch, market_state, articles_text)
                        if not commentary:
                            emit("epoch", "warn", "LLM synthesis failed — using template fallback")
                            commentary = generate_epoch_commentary(epoch, market_state)

                        # Include epoch config in meta for downstream use
                        publish("epoch", commentary, {
                            "epoch": epoch["name"],
                            "voice": epoch.get("voice", "Observer"),
                            "partitions": epoch.get("partitions", []),
                            "reflection_dial": epoch.get("reflection_dial", 0.4),
                            "market_state": market_state,
                            "articles_used": len(recent_articles),
                            "schedule_type": schedule_type,
                        })
                        last_epoch_name = epoch["name"]
                        emit("epoch", "epoch_speak", f"[{epoch.get('voice', 'Observer')}] {commentary[:100]}…")

            # -----------------------------
            # Events (trading days only for real-time events)
            # -----------------------------
            if ENABLE_EVENTS and VEXY_MODE in ["full", "events_only"] and trading_day:
                emit("event", "event_check", "Checking event triggers…")
                events = get_triggered_events(r_market)
                for event in events:
                    eid = f"{event['type']}:{event.get('id', '')}"
                    if eid not in last_event_ids:
                        publish("event", event["commentary"], event)
                        last_event_ids.add(eid)
                        if len(last_event_ids) > 100:
                            last_event_ids = set(list(last_event_ids)[-50:])
                        emit("event", "event_fire", f"{event['commentary'][:120]}…")

            # -----------------------------
            # Intel articles → commentary
            # On trading days: immediate publish
            # On non-trading days: batched based on article_trigger config
            # -----------------------------
            if ENABLE_INTEL and VEXY_MODE in ["full", "intel_only"]:
                if trading_day:
                    # Trading day: publish articles immediately
                    processed = process_intel_articles(r_system, emit)
                    if processed:
                        emit("intel", "ok", f"Published {processed} intel update(s)")
                else:
                    # Non-trading day: use article batching logic
                    article_config = get_article_trigger_config(config)
                    min_articles = article_config.get("min_articles", 2)
                    batch_window = article_config.get("batch_window_minutes", 60) * 60  # to seconds
                    max_per_day = article_config.get("max_messages_per_day", 8)
                    cooldown = article_config.get("cooldown_minutes", 45) * 60  # to seconds

                    # Check if we're under the daily limit and past cooldown
                    now_ts = time.time()
                    can_publish = (
                        daily_article_count < max_per_day and
                        (now_ts - last_article_publish) >= cooldown
                    )

                    if can_publish:
                        # Check for new articles (don't publish, just count)
                        recent_articles = article_reader.get_recent_articles(
                            max_count=10,
                            max_age_hours=batch_window / 3600,
                        )

                        if recent_articles:
                            # Start or continue batch window
                            if article_batch_start is None:
                                article_batch_start = now_ts
                                article_batch_count = len(recent_articles)
                                emit("intel", "info", f"Starting article batch: {article_batch_count} articles")
                            else:
                                article_batch_count = len(recent_articles)

                            # Check if batch criteria met
                            window_elapsed = now_ts - article_batch_start
                            if article_batch_count >= min_articles or window_elapsed >= batch_window:
                                # Publish batch commentary
                                processed = process_intel_articles(r_system, emit)
                                if processed:
                                    daily_article_count += 1
                                    last_article_publish = now_ts
                                    article_batch_start = None
                                    article_batch_count = 0
                                    emit("intel", "ok", f"Published article batch ({daily_article_count}/{max_per_day} today)")

            cycle_time = time.time() - cycle_start
            emit("cycle", "cycle", f"Cycle complete in {cycle_time:.1f}s — sleeping {int(loop_sleep_sec)}s")

            await asyncio.sleep(loop_sleep_sec)

    except asyncio.CancelledError:
        logger.info("orchestrator cancelled (shutdown)", emoji="🛑")
        emit("system", "warn", "Orchestrator cancelled, shutting down…")
        raise
    except Exception as e:
        logger.error(f"orchestrator fatal error: {e}", emoji="❌")
        emit("system", "fail", f"Fatal error in orchestrator: {e}")
        raise
    finally:
        logger.info("orchestrator exiting", emoji="✅")
        emit("system", "ok", "Orchestrator exiting.")
