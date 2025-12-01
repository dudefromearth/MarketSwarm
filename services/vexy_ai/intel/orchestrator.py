#!/usr/bin/env python3
"""
vexy_orchestrator.py — Vexy AI Play-by-Play Engine
Updated to print structured emoji-rich stdout lines:
[timestamp][component|process][emoji] message
"""

import os
import time
import redis
from datetime import datetime

from .epochs import should_speak_epoch
from .events import get_triggered_events
from .publisher import publish
from .intel_feed import process_intel_articles

# Redis connections
r_system = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)
r_market = redis.Redis(host="127.0.0.1", port=6380, decode_responses=True)

# Vexy mode control
VEXY_MODE = os.getenv("VEXY_MODE", "full").lower()

# Emoji map for common message types
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


def emit(step: str, emoji_key: str, msg: str):
    """Unified stdout print format with emoji selection.
    Format: [timestamp][component|step][emoji] message
    """
    ts = datetime.utcnow().strftime("%H:%M:%S")
    emoji = EMOJI.get(emoji_key, "📘")
    print(f"[{ts}] [vexy_ai|{step}] {emoji} {msg}")


# Stage switches

def flag(name: str, default: int = 1) -> int:
    val = r_system.get(f"pipeline:switch:{name}")
    if val is not None:
        return int(val)
    return int(os.getenv(f"VEXY_{name.upper()}", str(default)) == "1")


ENABLE_EPOCHS = flag("epochs", 1)
ENABLE_EVENTS = flag("events", 1)
ENABLE_INTEL = flag("intel", 1)

# Global state
last_epoch_name = None
last_event_ids = set()


def run_orchestrator(svc: str, setup_info: dict, truth: dict):
    global last_epoch_name, last_event_ids

    emit("startup", "startup", "Vexy AI Play-by-Play Engine starting")
    emit("config", "config", f"VEXY_MODE={VEXY_MODE}")
    emit("config", "config", f"Epochs={'YES' if ENABLE_EPOCHS else 'NO'}")
    emit("config", "config", f"Events={'YES' if ENABLE_EVENTS else 'NO'}")
    emit("config", "config", f"Intel feed={'YES' if ENABLE_INTEL else 'NO'}")

    while True:
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        cycle_start = time.time()

        # Epochs
        if ENABLE_EPOCHS and VEXY_MODE in ["full", "epochs_only"]:
            emit("epoch", "epoch_check", "Checking epoch triggers…")
            epoch = should_speak_epoch(current_time)
            if epoch and epoch["name"] != last_epoch_name:
                publish("epoch", epoch["commentary"], {"epoch": epoch["name"]})
                last_epoch_name = epoch["name"]
                emit(
                    "epoch", "epoch_speak", f"{epoch['commentary'][:120]}…"
                )

        # Events
        if ENABLE_EVENTS and VEXY_MODE in ["full", "events_only"]:
            emit("event", "event_check", "Checking event triggers…")
            events = get_triggered_events(r_market)
            for event in events:
                eid = f"{event['type']}:{event.get('id','')}"
                if eid not in last_event_ids:
                    publish("event", event["commentary"], event)
                    last_event_ids.add(eid)
                    if len(last_event_ids) > 100:
                        last_event_ids = set(list(last_event_ids)[-50:])
                    emit(
                        "event",
                        "event_fire",
                        f"{event['commentary'][:120]}…",
                    )

        # Intel articles → play-by-play commentary
        if ENABLE_INTEL and VEXY_MODE in ["full", "intel_only", "events_only", "epochs_only"]:
            processed = process_intel_articles(r_system, emit)
            if processed:
                emit("intel", "ok", f"Published {processed} intel update(s) from vexy:intake")

        cycle_time = time.time() - cycle_start
        emit("cycle", "cycle", f"Cycle complete in {cycle_time:.1f}s — sleeping 60s")
        time.sleep(60)
