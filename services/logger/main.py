import asyncio
import os

from heartbeat import start_heartbeat
from root.common.logger import run_logger

async def main_async():
    print("Logger: Starting async...")
    await start_heartbeat()
    await run_logger(redis_url=os.environ.get('REDIS_MAIN_URL', 'redis://main-redis:6379'), log_file='/app/logs/app.log')

if __name__ == '__main__':
    asyncio.run(main_async())