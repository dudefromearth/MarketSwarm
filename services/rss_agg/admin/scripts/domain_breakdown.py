import redis
from urllib.parse import urlparse

r = redis.Redis(host='localhost', port=6379, decode_responses=True)
uids = r.zrange("rss:index", 0, -1)
domains = {}
for uid in uids:
    item = r.hgetall(f"rss:item:{uid}")
    url = item.get('url', '')
    if url:
        domain = urlparse(url).netloc.replace('www.', '')
        domains[domain] = domains.get(domain, 0) + 1
print("Domain Breakdown:")
for domain, count in sorted(domains.items(), key=lambda x: x[1], reverse=True):
    print(f"{domain}: {count}")