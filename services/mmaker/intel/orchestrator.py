import asyncio
import json
import os
from typing import Any, Dict

import logutil  # services/mmaker/logutil.py

# Absolute imports for strategies (robust across contexts)
from services.mmaker.strategies.butterfly import build_butterfly_grid_from_chain
from services.mmaker.strategies.vertical import build_vertical_grid_from_chain

# Read debug flag from environment once at import time
DEBUG_ENABLED = os.getenv("DEBUG_MMAKER", "false").lower() == "true"


class ModelTransformer:
    """Pluggable base: Consume queue, transform raw trade to model schema, publish."""
    def __init__(self, config: Dict[str, Any], name: str = "base"):
        self.config = config
        self.name = name
        self.underlying = config['underlying']
        self.exp_iso = config['expiry_iso']
        self.debounce_sec = config.get('debounce_sec', 5.0)
        self.last_update = 0
        self.model_key = f"mm:models:{name}:{self.exp_iso}:latest"
        self.redis = config['redis_market']  # From setup/config

    async def consume(self, queue: asyncio.Queue) -> None:
        while True:
            try:
                trade = await queue.get()
                await self._transform_and_publish(trade)
                queue.task_done()
            except Exception as e:
                if DEBUG_ENABLED:
                    logutil.log(self.name, "DEBUG", "⚠️", f"Transformer error: {e}")

    async def _transform_and_publish(self, trade: Dict[str, Any]) -> None:
        now = asyncio.get_event_loop().time()
        if now - self.last_update < self.debounce_sec:
            return

        # Quick chain update (substrate for models)
        await self._update_chain_snapshot(trade)

        # Build schema (override in subclass)
        model_data = await self._build_model_schema(trade)

        # Publish to endpoint (SSE-ready)
        await self.redis.set(self.model_key, json.dumps(model_data))
        self.last_update = now

    async def _update_chain_snapshot(self, trade: Dict[str, Any]) -> None:
        contract = trade.get('contract')
        if not contract:
            return
        snap_key = f"CHAIN:{self.underlying}:EXP:{self.exp_iso}:latest"
        pointer = await self.redis.get(snap_key)
        if pointer:
            snap_raw = await self.redis.get(pointer)
            if snap_raw:
                snap = json.loads(snap_raw)
                for c in snap.get('contracts', []):
                    if c.get('details', {}).get('symbol') == contract:
                        c['last_trade'] = {
                            'price': float(trade.get('price', 0)),
                            'size': int(trade.get('size', 0)),
                            'ts': int(trade.get('ts', 0))
                        }
                        await self.redis.set(pointer, json.dumps(snap))
                        break

    async def _build_model_schema(self, trade: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError("Subclass implements schema build")


class ButterflyTransformer(ModelTransformer):
    name = "butterfly"

    async def _build_model_schema(self, trade: Dict[str, Any]) -> Dict[str, Any]:
        # Call your builder—outputs grid schema
        await build_butterfly_grid_from_chain(
            redis_url=self.redis.connection_pool.connection_kwargs.get('url'),
            underlying=self.underlying,
            exp_iso=self.exp_iso,
            strike_step=self.config.get('strike_step', 5.0)
        )
        # Fetch the built grid as schema
        grid_key = f"mm:{self.underlying}:butterfly:{self.exp_iso}:grid"
        raw_grid = await self.redis.get(grid_key)
        return json.loads(raw_grid) if raw_grid else {}


class VerticalTransformer(ModelTransformer):
    name = "vertical"

    async def _build_model_schema(self, trade: Dict[str, Any]) -> Dict[str, Any]:
        # Call vertical builder—outputs grid schema
        await build_vertical_grid_from_chain(
            redis_url=self.redis.connection_pool.connection_kwargs.get('url'),
            underlying=self.underlying,
            exp_iso=self.exp_iso,
            strike_step=self.config.get('strike_step', 5.0)
        )
        # Fetch the built grid as schema
        grid_key = f"mm:{self.underlying}:vertical:{self.exp_iso}:grid"
        raw_grid = await self.redis.get(grid_key)
        return json.loads(raw_grid) if raw_grid else {}


class ModelOrchestrator:
    """Reactive Streams core: XREAD raw → queue → parallel transforms → models."""
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.redis = config['redis_market']
        self.raw_stream_key = f"massive:trades:{config['underlying']}:{config['expiry_yyyymmdd']}"
        self.internal_queue = asyncio.Queue(maxsize=config.get('queue_maxsize', 1000))
        # Registry: List of transformers—plug more here
        self.transformers = [
            ButterflyTransformer(config),
            VerticalTransformer(config),
            # e.g., QuotesTransformer(config)
        ]
        self.consumer_tasks = []
        self.consume_task = None

    async def start(self):
        # Spawn parallel consumers
        self.consumer_tasks = [
            asyncio.create_task(t.consume(self.internal_queue)) for t in self.transformers
        ]
        # Start raw stream consumer
        self.consume_task = asyncio.create_task(self._consume_raw_stream())

    async def stop(self):
        if self.consume_task:
            self.consume_task.cancel()
        for task in self.consumer_tasks:
            task.cancel()
        await self.internal_queue.join()

    async def _consume_raw_stream(self):
        """XREAD raw trades → enqueue for transforms."""
        while True:
            try:
                # Block for new trades, batch up to 10
                streams = await self.redis.xread(
                    {self.raw_stream_key: '$'}, block=1000, count=10
                )
                for _, messages in streams:
                    for msg_id, fields in messages:
                        # Rebuild trade dict from fields
                        trade = dict(fields)
                        # Parse any JSON fields (e.g., conditions)
                        for k, v in trade.items():
                            if isinstance(v, str) and v.startswith('{'):
                                try:
                                    trade[k] = json.loads(v)
                                except:
                                    pass
                        await self.internal_queue.put(trade)
                        # Ack after enqueue (consumer group optional)
                        await self.redis.xack(self.raw_stream_key, 'model_maker_group', msg_id)
            except asyncio.CancelledError:
                break
            except Exception as e:
                if DEBUG_ENABLED:
                    logutil.log("orchestrator", "DEBUG", "⚠️", f"Raw stream consume error: {e}")
                await asyncio.sleep(1)


async def run(config: Dict[str, Any]) -> None:
    """
    Long-running orchestrator loop.

    This is the generic template:
      - Identifies the service from config["service_name"]
      - Emits INFO / ERROR logs always
      - Emits DEBUG logs only when DEBUG_MMAKER=true
      - Runs until cancelled by the main service loop
    """
    service_name = config.get("service_name", "unknown-service")

    logutil.log(service_name, "INFO", "🚀", "orchestrator starting")

    # Wire in the new setup: Create and start ModelOrchestrator
    orchestrator = ModelOrchestrator(config)
    try:
        await orchestrator.start()

        while True:
            # Main loop: Keep alive until cancelled (orchestrator runs async)
            if DEBUG_ENABLED:
                logutil.log(service_name, "DEBUG", "⏱️", "orchestrator tick")

            await asyncio.sleep(1.0)  # Light poll; adjust if needed

    except asyncio.CancelledError:
        # Normal shutdown path
        logutil.log(service_name, "INFO", "🛑", "orchestrator cancelled (shutdown)")
        await orchestrator.stop()
        raise

    except Exception as e:
        # Bubble up after logging – main loop will decide what to do
        logutil.log(service_name, "ERROR", "❌", f"orchestrator fatal error: {e}")
        await orchestrator.stop()
        raise

    finally:
        logutil.log(service_name, "INFO", "✅", "orchestrator exiting")