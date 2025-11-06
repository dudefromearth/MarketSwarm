from rss_agg.scripts import rss_audit
from rss_agg.admin.base import BaseStrategy
from rss_agg.admin.registry import register

@register
class RSSAuditStrategy(BaseStrategy):
    name = "rss_audit"
    description = "Inspect quarantined RSS items and generate source quality report"

    def execute(self, *args, **kwargs):
        rss_audit.main()