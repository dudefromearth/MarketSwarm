import redis
import json
import os
from datetime import datetime

class RedisChainExplorer:
    """
    Simple tool to fetch and display 2-3 records from Redis options chain snapshots.
    """
    def __init__(self, redis_url=None):
        self.redis_url = redis_url or os.environ.get('REDIS_MAIN_URL', 'redis://localhost:6379')
        self.r = redis.from_url(self.redis_url)

    def get_spot(self, chain_data):
        """
        Extract spot from first record's underlying_asset.
        """
        if chain_data and chain_data:
            first_item = list(chain_data.values())[0]
            ua = first_item.get('underlying_asset', {})
            return ua.get('price', None)
        return None

    def explore_chain(self, symbol='SPY', num_records=3):
        """
        Fetch chain from Redis, show 2-3 records in table format.
        """
        key = f'options:chain:{symbol}'
        chain_str = self.r.get(key)
        if not chain_str:
            print(f"No chain data for {symbol}")
            return

        chain = json.loads(chain_str)
        spot = self.get_spot(chain)
        atm = round(spot) if spot else 'N/A'
        print(f"Exploring {symbol} chain – Spot: {spot}, ATM: {atm}")
        print("Records (2-3):")
        count = 0
        for strike, data in sorted(chain.items()):
            if count >= num_records:
                break
            call = data.get('call', {})
            put = data.get('put', {})
            call_bid = call.get('bid', 'N/A')
            call_ask = call.get('ask', 'N/A')
            put_bid = put.get('bid', 'N/A')
            put_ask = put.get('ask', 'N/A')
            ts = data.get('ts', 'N/A')
            print(f"Strike {strike}: Call (bid/ask: {call_bid}/{call_ask}), Put (bid/ask: {put_bid}/{put_ask}), TS: {ts}")
            count += 1
        if count == 0:
            print("No records in chain")

if __name__ == '__main__':
    explorer = RedisChainExplorer()
    explorer.explore_chain('SPY')