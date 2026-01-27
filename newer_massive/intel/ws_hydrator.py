from __future__ import annotations

import asyncio
import json
import time
from typing import Dict, Any, Optional, Set

from redis.asyncio import Redis


class WsHydrator:
    def __init__(
        self,
        config: Dict[str, Any],
        logger,
        redis: Optional[Redis] = None,
    ):
        self.logger = logger
        self.config = config

        self.redis = redis or Redis.from_url(
            config["buses"]["market-redis"]["url"],
            decode_responses=True,
        )

        self.ws_stream_key = "massive:ws:stream"
        self.surface_latest_prefix = "massive:surface:"  # e.g., massive:surface:I:SPX:latest
        self.epoch_dirty_set = "epoch:dirty"  # kept for builder trigger (optional)

        self.group = "ws_hydrator"
        self.consumer = f"hydrator-{int(time.time())}"

        self.batch_size = int(config.get("MASSIVE_WS_HYDRATE_BATCH", "200"))
        self.poll_timeout_ms = int(config.get("MASSIVE_WS_HYDRATE_BLOCK_MS", "1000"))

        self.logger.info("[WS HYDRATOR INIT] ready", emoji="💧")

    async def run(self, stop_event: asyncio.Event) -> None:
        await self._ensure_consumer_group()
        self.logger.info("[WS HYDRATOR RUN] starting", emoji="🚀")

        while not stop_event.is_set():
            try:
                await self._hydrate_once()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"[WS HYDRATOR ERROR] {e}", emoji="💥")
                await asyncio.sleep(1)

        self.logger.info("[WS HYDRATOR STOP] stopped", emoji="🛑")

    async def _ensure_consumer_group(self) -> None:
        try:
            await self.redis.xgroup_create(
                self.ws_stream_key, self.group, id="0-0", mkstream=True
            )
        except Exception:
            pass

    async def _hydrate_once(self) -> None:
        resp = await self.redis.xreadgroup(
            groupname=self.group,
            consumername=self.consumer,
            streams={self.ws_stream_key: ">"},
            count=self.batch_size,
            block=self.poll_timeout_ms,
        )

        if not resp:
            return

        pipe = self.redis.pipeline(transaction=False)
        touched_symbols: Set[str] = set()

        for _, entries in resp:
            for msg_id, fields in entries:
                try:
                    await self._process_message(fields, pipe, touched_symbols)
                finally:
                    pipe.xack(self.ws_stream_key, self.group, msg_id)

        # Optional: trigger model rebuild if any symbol was touched
        for symbol in touched_symbols:
            pipe.publish("massive:surface:updated", symbol)

        await pipe.execute()

    async def _process_message(
        self,
        fields: Dict[str, str],
        pipe,
        touched_symbols: Set[str],
    ):
        payload = fields.get("payload")
        if not payload:
            return

        try:
            events = json.loads(payload)
        except Exception:
            return

        if not isinstance(events, list):
            return

        for e in events:
            pipe.incr("massive:ws:hydrate:seen")

            ts = e.get("t")

            pipe.hset(
                "massive:ws:hydrate:last_contract",
                mapping={
                    "sym": e.get("sym") or "",
                    "ts": ts if ts is not None else 0,
                    "raw_event": json.dumps(e, separators=(",", ":")),
                },
            )

            sym = e.get("sym")
            if not sym or not sym.startswith("O:"):
                continue

            parsed = self._parse_contract(sym)
            if not parsed:
                pipe.incr("massive:ws:hydrate:parse_fail")
                continue

            raw_underlying, strike = parsed
            if strike is None:
                continue

            norm_underlying = self._normalize_underlying(raw_underlying)

            # Use the latest surface hash for this symbol
            surface_key = f"{self.surface_latest_prefix}{norm_underlying}:latest"
            if not await self.redis.exists(surface_key):
                # No surface yet (startup lag) — skip silently
                continue

            contract_json = await self.redis.hget(surface_key, str(strike))
            if not contract_json:
                continue  # strike not in current surface

            contract = json.loads(contract_json)
            contract.update(
                {"last": e.get("p"), "size": e.get("s"), "ts": ts}
            )

            if contract.get("last") is None:
                pipe.incr("massive:ws:hydrate:null_skip")
                continue

            # Update the live surface in-place
            pipe.hset(surface_key, str(strike), json.dumps(contract))

            pipe.incr("massive:ws:hydrate:hydrated")

            touched_symbols.add(norm_underlying)

    def _normalize_underlying(self, underlying: str) -> str:
        if underlying.endswith("W"):
            underlying = underlying[:-1]

        if underlying in ("SPX", "NDX", "VIX"):
            return f"I:{underlying}"

        return underlying

    def _parse_contract(self, sym: str) -> Optional[tuple[str, float]]:
        try:
            body = sym[2:]
            for i, c in enumerate(body):
                if c.isdigit():
                    underlying = body[:i]
                    rest = body[i:]
                    break
            else:
                return None

            strike = float(rest[7:]) / 1000
            return underlying, strike

        except Exception:
            return None