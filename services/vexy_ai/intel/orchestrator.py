#!/usr/bin/env python3
"""
vexy_orchestrator.py — Vexy AI Play-by-Play Engine

New pattern:
  - Async entrypoint: async def run(config)
  - Called by main.py as `await orchestrator.run(config)`
  - Uses standard logging via logutil.log(...)
  - Preserves Vexy's emoji-rich emit() output as message voice.

Behavior:
  - Reads mode + stage switches from system-redis and env
  - Epoch commentary (epochs module)
  - Event commentary (events module)
  - Intel article commentary (intel_feed module)
  - Publishes via publisher.publish(...)
"""

from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, UTC
from typing import Any, Dict, Set

import redis

import logutil  # services/vexy_ai/logutil.py

from .epochs import should_speak_epoch
from .events import get_triggered_events
from .publisher import publish
from .intel_feed import process_intel_articles


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

    Format:
      [timestamp][vexy_ai|step] emoji message

    This is *not* system logging; it's the human-facing stream of commentary
    / status, separate from logutil's structured logs.
    """
    ts = datetime.now(UTC).strftime("%H:%M:%S")
    emoji = EMOJI.get(emoji_key, "📘")
    print(f"[{ts}][vexy_ai|{step}] {emoji} {msg}")


# Global state for de-duplication and context
last_epoch_name: str | None = None
last_event_ids: Set[str] = set()


def _flag(r_system: redis.Redis, name: str, default: int = 1) -> int:
    """
    Stage switches for Vexy:

    Priority:
      1. Redis key: pipeline:switch:<name>
      2. Env: VEXY_<NAME_UPPER>
      3. default
    """
    redis_key = f"pipeline:switch:{name}"
    val = r_system.get(redis_key)
    if val is not None:
        try:
            v = int(val)
            return v
        except ValueError:
            pass

    env_val = os.getenv(f"VEXY_{name.upper()}", str(default))
    return int(env_val == "1")


async def run(config: Dict[str, Any]) -> None:
    """
    Async orchestrator entrypoint for vexy_ai.

    Contract:
      - Called once by main.py (inside a service loop)
      - Runs until cancelled or an unrecoverable error occurs
      - Uses sync Redis clients internally (ok for now; may be
        migrated to redis.asyncio later if needed)
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

    r_system = redis.Redis.from_url(system_url, decode_responses=True)
    r_market = redis.Redis.from_url(market_url, decode_responses=True)

    # Stage switches
    ENABLE_EPOCHS = _flag(r_system, "epochs", 1)
    ENABLE_EVENTS = _flag(r_system, "events", 1)
    ENABLE_INTEL = _flag(r_system, "intel", 1)

    # ------------------------------------------------------------
    # Startup logs
    # ------------------------------------------------------------
    logutil.log(service_name, "INFO", "🚀", "orchestrator starting")
    logutil.log(service_name, "INFO", "⚙️", f"VEXY_MODE={VEXY_MODE}")
    logutil.log(
        service_name,
        "INFO",
        "⚙️",
        f"Epochs={'YES' if ENABLE_EPOCHS else 'NO'}, "
        f"Events={'YES' if ENABLE_EVENTS else 'NO'}, "
        f"Intel={'YES' if ENABLE_INTEL else 'NO'}",
    )

    emit("startup", "startup", "Vexy AI Play-by-Play Engine starting")
    emit("config", "config", f"VEXY_MODE={VEXY_MODE}")
    emit("config", "config", f"Epochs={'YES' if ENABLE_EPOCHS else 'NO'}")
    emit("config", "config", f"Events={'YES' if ENABLE_EVENTS else 'NO'}")
    emit("config", "config", f"Intel feed={'YES' if ENABLE_INTEL else 'NO'}")

    loop_sleep_sec = 60.0

    try:
        while True:
            cycle_start = time.time()
            now = datetime.now()
            current_time = now.strftime("%H:%M")

            # -----------------------------
            # Epochs
            # -----------------------------
            if ENABLE_EPOCHS and VEXY_MODE in ["full", "epochs_only"]:
                emit("epoch", "epoch_check", "Checking epoch triggers…")
                epoch = should_speak_epoch(current_time)
                if epoch and epoch["name"] != last_epoch_name:
                    publish("epoch", epoch["commentary"], {"epoch": epoch["name"]})
                    last_epoch_name = epoch["name"]
                    emit(
                        "epoch",
                        "epoch_speak",
                        f"{epoch['commentary'][:120]}…",
                    )

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
                        # prevent unbounded growth
                        if len(last_event_ids) > 100:
                            last_event_ids = set(list(last_event_ids)[-50:])
                        emit(
                            "event",
                            "event_fire",
                            f"{event['commentary'][:120]}…",
                        )

            # -----------------------------
            # Intel articles → commentary
            # -----------------------------
            if ENABLE_INTEL and VEXY_MODE in [
                "full",
                "intel_only",
                "events_only",
                "epochs_only",
            ]:
                processed = process_intel_articles(r_system, emit)
                if processed:
                    emit(
                        "intel",
                        "ok",
                        f"Published {processed} intel update(s) from vexy:intake",
                    )

            cycle_time = time.time() - cycle_start
            emit(
                "cycle",
                "cycle",
                f"Cycle complete in {cycle_time:.1f}s — sleeping {int(loop_sleep_sec)}s",
            )

            # Async-friendly sleep
            await asyncio.sleep(loop_sleep_sec)

    except asyncio.CancelledError:
        logutil.log(service_name, "INFO", "🛑", "orchestrator cancelled (shutdown)")
        emit("system", "warn", "Orchestrator cancelled, shutting down…")
        raise
    except Exception as e:
        logutil.log(service_name, "ERROR", "❌", f"orchestrator fatal error: {e}")
        emit("system", "fail", f"Fatal error in orchestrator: {e}")
        raise
    finally:
        logutil.log(service_name, "INFO", "✅", "orchestrator exiting")
        emit("system", "ok", "Orchestrator exiting.")