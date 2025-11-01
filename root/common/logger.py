import json
from datetime import datetime, timezone
from redis.asyncio import Redis

STATUS_EMOJI = {
    'INFO': 'ℹ️',
    'WARN': '⚠️',
    'ERROR': '❌',
    'DEBUG': '🔍'
}

def format_log(status, description, context=''):
    ts = datetime.now(timezone.utc).isoformat() + 'Z'
    emoji = STATUS_EMOJI.get(status, '❓')
    return f"[{ts}] {status} {emoji} {description}: {context}"

async def run_logger(redis_url='redis://main-redis:6379', log_file='/app/logs/app.log'):
    redis = Redis.from_url(redis_url)
    pubsub = redis.pubsub()
    await pubsub.subscribe('heartbeats')
    async for message in pubsub.listen():
        if message['type'] == 'message':
            data = json.loads(message['data'])
            log_msg = format_log('INFO', 'Heartbeat received', f"{data['identity']} at {data['ts']}")
            with open(log_file, 'a') as f:
                f.write(log_msg + '\n')
            print(log_msg)