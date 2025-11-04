import redis

r = redis.Redis(host='localhost', port=6379, decode_responses=True)
uids = r.zrange("rss:index", 0, -1)
ttl = 86400  # 24h
for uid in uids:
    r.expire(f'rss:item:{uid}', ttl)
r.expire('rss:index', ttl)
r.expire('rss:queue', ttl)
print(f"Updated TTL to 24h on {len(uids)} items + index/queue")