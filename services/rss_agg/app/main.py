import asyncio
from shared.provider_base_service import ProviderBaseService
from rss_core import poll_feeds_once  # assuming your aggregator logic lives here


class RssAggService(ProviderBaseService):
    async def run_cycle(self):
        """Main loop for fetching and publishing feeds."""
        system_redis = self.redis_clients.get("system-redis")
        if not system_redis:
            print("[rss_agg] ❌ No Redis connection found")
            return 0

        print("[rss_agg] 🔁 Polling feeds from Truth config...")
        new_items = await poll_feeds_once(system_redis)
        print(f"[rss_agg] ✅ Published {new_items} new feed items.")
        return new_items


async def main_async():
    service = RssAggService("rss_agg")
    await service.start()


if __name__ == "__main__":
    asyncio.run(main_async())