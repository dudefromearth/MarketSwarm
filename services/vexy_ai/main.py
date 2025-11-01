import asyncio
import os
from heartbeat import start_heartbeat
from redis.asyncio import Redis

async def run_mesh():
    redis = Redis.from_url(os.environ.get('REDIS_MAIN_URL', 'redis://main-redis:6379'))
    while True:
        tasks = await redis.blpop(['mesh_tasks'], timeout=1)
        if tasks:
            await redis.publish('vexy_ai', tasks[1])  # Dispatch stub
            print(f"Dispatched: {tasks[1]}")
        await asyncio.sleep(0.1)

async def main_async():
    print("Mesh Coordinator: Starting async...")
    await start_heartbeat()
    await run_mesh()

if __name__ == '__main__':
    asyncio.run(main_async())