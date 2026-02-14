"""
Hydration Triggers — Listens for events that should trigger snapshot hydration.

Trigger types:
1. Presence detected (user:presence pub/sub on market-redis)
2. Session start (first interaction after inactivity)
3. State change (trade opened/closed, regime change)
4. Snapshot expired (TTL lapsed, checked on-demand)

Phase 1: Presence-based only. Other triggers added in Phase 3.
"""

import asyncio
import json
from typing import Any, Callable, Optional


class PresenceListener:
    """Subscribes to user:presence on market-redis and triggers hydration."""

    def __init__(self, market_redis: Any, on_presence: Callable, logger: Any):
        """
        Args:
            market_redis: Sync redis client for market-redis
            on_presence: Callback(user_id, tier) called on presence event
            logger: LogUtil instance
        """
        self._redis = market_redis
        self._on_presence = on_presence
        self._logger = logger
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Start listening for presence events."""
        self._running = True
        self._task = asyncio.create_task(self._listen_loop())
        self._logger.info("Presence listener started (channel: user:presence)")

    async def stop(self):
        """Stop listening."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _listen_loop(self):
        """Main pub/sub listen loop."""
        try:
            pubsub = self._redis.pubsub()
            pubsub.subscribe("user:presence")

            while self._running:
                msg = pubsub.get_message(timeout=1.0)
                if msg and msg["type"] == "message":
                    try:
                        data = json.loads(msg["data"]) if isinstance(msg["data"], str) else {}
                        user_id = data.get("user_id")
                        tier = data.get("tier", "observer")
                        if user_id:
                            await self._on_presence(user_id, tier)
                    except Exception as e:
                        self._logger.warning(f"Presence event parse error: {e}")

                await asyncio.sleep(0.1)  # Yield to event loop

        except asyncio.CancelledError:
            pass
        except Exception as e:
            self._logger.error(f"Presence listener error: {e}")
        finally:
            try:
                pubsub.unsubscribe("user:presence")
                pubsub.close()
            except Exception:
                pass
