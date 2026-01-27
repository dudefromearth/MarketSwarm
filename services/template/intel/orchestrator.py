# services/template/orchestrator.py

import asyncio
from typing import Dict, Any
from .worker import Worker


async def run(config: Dict[str, Any], redis_clients: Dict[str, Any], logger):
    """
    Universal orchestrator template:

    - Creates Worker instance
    - Subscribes to all input redis channels
    - Hands messages to Worker.handle()
    """

    inputs = config.get("inputs", [])

    worker = Worker(logger)

    listeners = []

    # Subscribe to input feeds
    for inp in inputs:
        bus = inp["bus"]
        key = inp["key"]
        redis = redis_clients[bus]

        ps = redis.pubsub()
        await ps.subscribe(key)
        listeners.append(ps)

        logger.info(f"subscribed to {bus} → {key}", emoji="📡")

    logger.info("orchestrator loop running", emoji="▶️")

    try:
        while True:
            for ps in listeners:
                msg = await ps.get_message(ignore_subscribe_messages=True)
                if msg:
                    await worker.handle(msg["data"])
            await asyncio.sleep(0.001)

    except asyncio.CancelledError:
        logger.warn("orchestrator stopping", emoji="🛑")
        raise

    except Exception as e:
        logger.error(f"orchestrator exception: {e}", emoji="💥")
        raise