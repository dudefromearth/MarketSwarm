import redis
from collections import Counter
r = redis.Redis(host='localhost', port=6379, decode_responses=True)
uids = r.zrange("rss:index", 0, -1)
terms = []
for uid in uids:
    item = r.hgetall(f"rss:item:{uid}")
    abstract = item.get('abstract', '')
    words = abstract.lower().split()
    terms.extend([w for w in words if len(w) > 3 and w.isalpha()])
top_terms = Counter(terms).most_common(20)
print("Top Keywords in Abstracts:")
for term, count in top_terms:
    print(f"{term}: {count}")