import asyncio
import json
import os
import time
from redis.asyncio import Redis

async def start_heartbeat():
    redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379')  # Use REDIS_URL, fallback local for standalone
    redis = Redis.from_url(redis_url)
    try:
        truth_json = await redis.get('truth')
        truth = json.loads(truth_json or '{}')
        hb_config = truth.get('heartbeats', {}).get(os.environ.get('SERVICE_ID', 'unknown'), {})
        identity = hb_config.get('id', os.environ.get('SERVICE_ID', 'unknown'))
        frequency = hb_config.get('frequency', 10)
    except Exception as e:
        print(f"Config error: {e} – fallback")
        identity = os.environ.get('SERVICE_ID', 'unknown')
        frequency = 10

    async def pulse():
        while True:
            status = "running"
            msg = json.dumps({
                "identity": identity,
                "status": status,
                "ts": time.time(),
                "container_id": os.environ.get('HOSTNAME', 'unknown')
            })
            await redis.publish('heartbeats', msg)
            print(f"Heartbeat published: {msg}")
            await asyncio.sleep(frequency)

    asyncio.create_task(pulse())