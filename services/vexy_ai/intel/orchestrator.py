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
from .publisher import publish
from .intel_feed import process_intel_articles
from .market_reader import MarketReader


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

    # Market data reader (consumes Massive models)
    market_reader = MarketReader(r_market, logger)

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

    loop_sleep_sec = float(config.get("VEXY_LOOP_SLEEP_SEC", "60"))

    try:
        while True:
            cycle_start = time.time()
            now = datetime.now()
            current_time = now.strftime("%H:%M")

            # -----------------------------
            # Epochs (with market data)
            # -----------------------------
            if ENABLE_EPOCHS and VEXY_MODE in ["full", "epochs_only"]:
                emit("epoch", "epoch_check", "Checking epoch triggers…")
                epoch = should_speak_epoch(current_time)
                if epoch and epoch["name"] != last_epoch_name:
                    # Fetch current market state
                    market_state = market_reader.get_market_state()

                    # Generate rich commentary
                    commentary = generate_epoch_commentary(epoch, market_state)

                    publish("epoch", commentary, {
                        "epoch": epoch["name"],
                        "market_state": market_state,
                    })
                    last_epoch_name = epoch["name"]
                    emit("epoch", "epoch_speak", f"{commentary[:120]}…")

            # -----------------------------
            # Events
            # -----------------------------
            if ENABLE_EVENTS and VEXY_MODE in ["full", "events_only"]:
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
            # -----------------------------
            if ENABLE_INTEL and VEXY_MODE in ["full", "intel_only"]:
                processed = process_intel_articles(r_system, emit)
                if processed:
                    emit("intel", "ok", f"Published {processed} intel update(s)")

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
