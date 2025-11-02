import redis, json, os

def get_redis(url=os.environ.get('REDIS_MAIN_URL', 'redis://localhost:6379')):
    return redis.Redis.from_url(url)

def load_truth(r, hostname='localhost'):
    return json.loads(r.get(f'Truth:canonical{hostname}') or '{}')