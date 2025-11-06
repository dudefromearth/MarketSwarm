from rss_agg.admin.base import BaseStrategy, R
from rss_agg.admin.registry import register

@register
class InspectSchemaStrategy(BaseStrategy):
    name = "inspect_schema"
    description = "Inspect current Redis schema and key states"

    def execute(self, *args, **kwargs):
        r = R()
        ver = r.get("rss:schema_version") or "Not initialized"
        keys = r.keys("rss:*")
        print(f"Schema Version: {ver}")
        print(f"Keys: {list(keys)}")
        for key in keys:
            if key == "rss:index":
                print(f"{key}: {r.zrange(key, 0, -1)} (sample)")
            elif key == "rss:queue":
                print(f"{key}: Length {r.xlen(key)}")