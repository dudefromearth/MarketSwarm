import redis
from urllib.parse import urlparse
from collections import defaultdict, Counter  # Added Counter

r = redis.Redis(host='localhost', port=6379, decode_responses=True)
uids = r.zrange("rss:index", 0, -1)
domain_bias = defaultdict(lambda: Counter())
for uid in uids:
    item = r.hgetall(f"rss:item:{uid}")
    url = item.get('url', '')
    abstract = item.get('abstract', '').lower()
    domain = urlparse(url).netloc.replace('www.', '')
    for word in ['hawkish', 'dovish', 'rate', 'fomc']:
        count = abstract.count(word)
        domain_bias[domain][word] += count
print("Domain Bias Breakdown:")
for domain, bias in domain_bias.items():
    print(f"{domain}: {dict(bias)}")