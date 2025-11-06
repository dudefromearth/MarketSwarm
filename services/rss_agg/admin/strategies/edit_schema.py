from rss_agg.admin.base import BaseStrategy, R
from rss_agg.admin.registry import register
import os, json

@register
class EditSchemaStrategy(BaseStrategy):
    name = "edit_schema"
    description = "Initialize or edit Redis schema"

    def execute(self, *args, **kwargs):
        version = args[0] if args else None
        path = f"schema/schema_v{version}.json" if version else "schema/feeds.json"
        if not os.path.exists(path):
            print(f"Schema {path} not found")
            return
        r = R()
        with open(path, 'r') as f:
            schema = json.load(f)
        pipe = r.pipeline()
        for k in schema['keys']:
            key = k['name']
            t = k['type']
            if t == 'SET': pipe.sadd(key, '')
            elif t == 'ZSET': pipe.zadd(key, {'placeholder': 0})
            elif t == 'STREAM': pipe.xadd(key, {'uid': 'init', 'abstract': 'ready'})
        pipe.execute()
        r.set("rss:schema_version", schema['version'])
        r.bgsave()
        print(f"Schema loaded: v{schema['version']}")