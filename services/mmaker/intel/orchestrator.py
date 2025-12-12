# services/mmaker/intel/orchestrator.py

import asyncio
import json
from typing import Any, Dict

from redis.asyncio import Redis

from .tile_router import TileRouter
from .single_transformer import SingleTransformer
from .vertical_transformer import VerticalTransformer
from .butterfly_transformer import ButterflyTransformer
from .tile_inspector import TileInspector


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

async def _ensure_models(redis: Redis, ul: str, exp: str):
    """
    Ensure Redis tile hashes exist for:
      single
      vertical
      butterfly
    """
    keys = [
        f"mm:tiles:{ul}:{exp}:single",
        f"mm:tiles:{ul}:{exp}:vertical",
        f"mm:tiles:{ul}:{exp}:butterfly",
    ]

    for key in keys:
        exists = await redis.exists(key)
        if not exists:
            # HSET requires minimally 1 field
            await redis.hset(
                key,
                "_init",
                json.dumps({"tile": {}, "hash": ""})
            )


def _extract_ul_exp(config: Dict[str, Any]):
    dk = config.get("domain_keys", [])
    if len(dk) < 2:
        raise RuntimeError("mmaker domain_keys must include UL and EXP")
    return dk[0], dk[1]


def _extract_redis_inputs(config: Dict[str, Any]):
    inputs = config.get("inputs", [])
    subs = []
    for inp in inputs:
        subs.append((inp["redis_url"], inp["key"]))
    return subs


# ------------------------------------------------------------
# Main Orchestrator with Live Debug
# ------------------------------------------------------------

async def run(config: Dict[str, Any]):
    """
    mmaker orchestrator:

    - Build transformer stack (Single, Vertical, Butterfly)
    - Create TileRouter dependency engine
    - Bind to Redis pubsub for trades
    - Dispatch to router
    - Live Debug: optional tile inspection every N trades
    """

    service_name = config.get("service_name", "mmaker")

    # --------------------------------------------------------
    # Resolve UL + EXP
    # --------------------------------------------------------
    ul, exp = _extract_ul_exp(config)

    # --------------------------------------------------------
    # Shared market Redis
    # --------------------------------------------------------
    primary_redis: Redis = config["shared_resources"]["primary_redis"]

    # --------------------------------------------------------
    # Ensure model hashes exist
    # --------------------------------------------------------
    await _ensure_models(primary_redis, ul, exp)

    # --------------------------------------------------------
    # Transformers
    # --------------------------------------------------------
    vertical_widths = [5, 10, 15, 20]
    fly_widths = [5, 10, 15, 20]

    single = SingleTransformer(primary_redis, ul, exp)
    vertical = VerticalTransformer(primary_redis, ul, exp, vertical_widths)
    butterfly = ButterflyTransformer(primary_redis, ul, exp, fly_widths)

    # --------------------------------------------------------
    # Dependency Router
    # --------------------------------------------------------
    router = TileRouter(primary_redis, single, vertical, butterfly)

    # --------------------------------------------------------
    # Live Debug Inspector
    # --------------------------------------------------------
    inspector = TileInspector(primary_redis, ul, exp)
    debug_every = 250    # print inspection every 250 trades
    trade_count = 0

    # --------------------------------------------------------
    # Subscribe to trade feed
    # --------------------------------------------------------
    subs = _extract_redis_inputs(config)
    if not subs:
        raise RuntimeError("mmaker must subscribe to at least one market bus")

    redis_url, trade_key = subs[0]

    sub_redis = Redis.from_url(redis_url)
    pubsub = sub_redis.pubsub()
    await pubsub.subscribe(trade_key)

    print(f"[{service_name}] 🚦 subscribed to {redis_url} key={trade_key}")

    # --------------------------------------------------------
    # Ingestion Loop
    # --------------------------------------------------------
    try:
        async for msg in pubsub.listen():
            if msg is None or msg.get("type") != "message":
                continue

            raw = msg.get("data")
            if not raw:
                continue

            try:
                trade = json.loads(raw)
            except Exception:
                continue

            # Required fields
            if "cp" not in trade or "strike" not in trade or "price" not in trade:
                continue

            trade.setdefault("ts", trade.get("timestamp", 0))

            # Main dispatch
            await router.process_trade(trade)

            # ------------------------------------------------
            # Live Debug Hook
            # ------------------------------------------------
            trade_count += 1
            if trade_count % debug_every == 0:
                print(f"\n[{service_name}] 🔍 LIVE DEBUG — after {trade_count} trades")

                # Show 3 singles, 3 verticals, 3 butterflies
                singles = await inspector.inspect("single", limit=3)
                verts = await inspector.inspect("vertical", limit=3)
                flies = await inspector.inspect("butterfly", limit=3)

                print("  • Singles:")
                for row in singles:
                    print("    ", row)

                print("  • Verticals:")
                for row in verts:
                    print("    ", row)

                print("  • Butterflies:")
                for row in flies:
                    print("    ", row)

                print("")

    except asyncio.CancelledError:
        print(f"[{service_name}] stopping orchestrator")
        raise

    except Exception as e:
        print(f"[{service_name}] ERROR in orchestrator: {e}")
        await asyncio.sleep(0.5)
        raise