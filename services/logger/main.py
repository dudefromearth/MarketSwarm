import os, time, json, socket, asyncio
from redis.asyncio import Redis

SERVICE_ID = os.getenv("SERVICE_ID", "logger")
REDIS_MAIN_URL = os.getenv("REDIS_MAIN_URL", "redis://main-redis:6379")
HEARTBEAT_CHANNEL = os.getenv("HEARTBEAT_CHANNEL", "heartbeats")
HEARTBEAT_INTERVAL = float(os.getenv("HEARTBEAT_INTERVAL", "10"))

async def heartbeat_loop():
    redis = Redis.from_url(REDIS_MAIN_URL, decode_responses=True)
    container_id = socket.gethostname()
    while True:
        payload = {
            "identity": SERVICE_ID,
            "status": "running",
            "ts": time.time(),
            "container_id": container_id,
        }
        try:
            await redis.publish(HEARTBEAT_CHANNEL, json.dumps(payload))
            print(f"Heartbeat published: {payload}", flush=True)
        except Exception as e:
            # Don't die; log and retry next tick
            print(f"Heartbeat error: {e}", flush=True)
        await asyncio.sleep(HEARTBEAT_INTERVAL)

async def main():
    print(f"{SERVICE_ID}: starting heartbeat → {REDIS_MAIN_URL} channel={HEARTBEAT_CHANNEL}", flush=True)
    await heartbeat_loop()

if __name__ == "__main__":
    asyncio.run(main())