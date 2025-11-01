import json
import os
import redis
import time

def load_truth():
    r = redis.Redis.from_url(os.environ.get('REDIS_MAIN_URL', 'redis://main-redis:6379'))
    with open('truth.json', 'r') as f:
        truth = json.load(f)
    truth['core']['polygon_api_key'] = os.environ.get('POLYGON_API_KEY', truth['core'].get('polygon_api_key', ''))
    truth['core']['system_ts'] = int(time.time())
    r.set('truth', json.dumps(truth))
    print("Truth loaded: v" + truth['version'])

if __name__ == '__main__':
    load_truth()