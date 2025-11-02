import requests
import redis
import json
import time
import threading
import os
import signal
import sys
from datetime import date

class IndicesSpotUtility:
    """
    Utility class for fetching and extracting spot price from Polygon.io indices snapshot.
    Primary: 'value' from results[0].
    Fallback: 'session.close'.
    """
    def __init__(self, api_key=None):
        self.api_key = api_key or os.environ.get('POLYGON_API_KEY')
        if not self.api_key:
            raise ValueError("API key required – set POLYGON_API_KEY env")
        self.base_url = "https://api.polygon.io/v3/snapshot/indices"

    def get_spot(self, ticker='I:SPX', limit=1):
        """
        Fetch snapshot and extract spot price.
        Returns spot float or None if error/no data.
        """
        url = f"{self.base_url}?ticker={ticker}&limit={limit}&apikey={self.api_key}"
        resp = requests.get(url, timeout=10)
        print(f"Response for {ticker}: status {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            if 'results' in data and data['results']:
                first_item = data['results'][0]
                # Primary: value
                spot = first_item.get('value', None)
                if spot is not None:
                    print(f"Spot from value: {spot}")
                    return spot
                # Fallback: session.close
                session = first_item.get('session', {})
                spot = session.get('close', None)
                if spot is not None:
                    print(f"Spot from session.close: {spot}")
                    return spot
                print(f"No spot for {ticker}")
                return None
            print(f"No results for {ticker}")
            return None
        print(f"API error for {ticker}: {resp.status_code}")
        return None

def get_underlying_spot(snap_item):
    ua = snap_item.get("underlying_asset") or {}
    if "value" in ua:
        return ua["value"]
    session = snap_item.get("session", {})
    if "close" in session:
        return session["close"]
    lt = snap_item.get("last_trade") or {}
    if "price" in lt:
        return lt["price"]
    lq = snap_item.get("last_quote") or {}
    if "bid" in lq and "ask" in lq and lq["bid"] is not None and lq["ask"] is not None:
        return (lq["bid"] + lq["ask"]) / 2
    return None

# Global flag for graceful exit
shutdown_flag = threading.Event()

def signal_handler(sig, frame):
    print("Shutdown signal received – graceful exit...")
    shutdown_flag.set()
    sys.exit(0)

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

def start_snapshot():
    r = redis.Redis.from_url(os.environ.get('REDIS_MAIN_URL', 'redis://host.docker.internal:6379'))
    api_key = os.environ.get('POLYGON_API_KEY')
    symbols = ['SPY', 'SPX', 'QQQ', 'NDX']
    intervals = {'SPY': 1, 'SPX': 5, 'QQQ': 1, 'NDX': 5}

    util = IndicesSpotUtility(api_key="api_key")  # Utility for indices spot

    def snapshot():
        while not shutdown_flag.is_set():
            for symbol in symbols:
                # Get spot – use indices for SPX/NDX, options for SPY/QQQ
                if symbol in ['SPX', 'NDX']:
                    spot = util.get_spot(f'I:{symbol}')
                else:
                    # For equities, use options snapshot for spot
                    spot_url = f"https://api.polygon.io/v3/snapshot/options/{symbol}?limit=1&apikey={api_key}"
                    spot_resp = requests.get(spot_url)
                    spot = None
                    if spot_resp.status_code == 200:
                        spot_data = spot_resp.json()
                        if spot_data.get('results'):
                            first_item = spot_data['results'][0]
                            spot = get_underlying_spot(first_item)
                if spot is None:
                    spot = 0  # Fallback
                interval = intervals.get(symbol, 1)
                atm = round(spot / interval) * interval
                low = atm - 30 * interval
                high = atm + 30 * interval
                url = f"https://api.polygon.io/v3/snapshot/options/{symbol}?strike_price.gte={low}&strike_price.lte={high}&sort=strike_price&order=asc&limit=250&apiKey={api_key}"
                resp = requests.get(url)
                print(f"Response for {symbol}: status {resp.status_code}, spot {spot}, ATM {atm}, range {low}-{high}")
                if resp.status_code == 200:
                    data = resp.json()
                    if 'results' in data and data['results']:
                        chain = {}
                        for item in data['results']:
                            details = item.get('details', {})
                            strike = details.get('strike_price', None)
                            contract_type = details.get('contract_type', 'unknown')
                            if strike is not None and contract_type != 'unknown':
                                type_ = 'call' if contract_type == 'call' else 'put'
                                if strike not in chain:
                                    chain[strike] = {'call': {}, 'put': {}}
                                chain[strike][type_] = {
                                    'bid': item.get('bid', 0),
                                    'ask': item.get('ask', 0),
                                    'last': item.get('last_trade', {}).get('P', 0),
                                    'ts': time.time()
                                }
                        r.set(f'options:chain:{symbol}', json.dumps(chain))
                        print("Snapshot published for", symbol)
                    else:
                        print(f"No results for {symbol}")
                else:
                    print(f"API error for {symbol}: {resp.status_code}")
                shutdown_flag.wait(1)  # Sleep with flag check
        print("Snapshot thread exiting gracefully...")

    snap_thread = threading.Thread(target=snapshot, daemon=True)
    snap_thread.start()
    print("Snapshot thread started – infinite loop (Ctrl+C to stop)")
    try:
        while not shutdown_flag.is_set():
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown_flag.set()
        snap_thread.join(timeout=10)  # Wait for clean exit
        print("Graceful shutdown complete.")

if __name__ == '__main__':
    start_snapshot()