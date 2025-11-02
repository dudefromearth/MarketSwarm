import requests
import redis
import json
import time
import threading
import os

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

def start_snapshot():
    r = redis.Redis.from_url(os.environ.get('REDIS_MAIN_URL', 'redis://host.docker.internal:6379'))
    api_key = os.environ.get('POLYGON_API_KEY')
    symbols = ['SPY', 'SPX', 'QQQ', 'NDX']
    intervals = {'SPY': 1, 'SPX': 5, 'QQQ': 1, 'NDX': 5}

    def snapshot():
        while True:
            for symbol in symbols:
                # Seed call for spot (limit=1)
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
                url = f"https://api.polygon.io/v3/snapshot/options/{symbol}?strike_price.gte={low}&strike_price.lte={high}&sort=strike_price&order=asc&limit=250&apikey={api_key}"
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
            time.sleep(1)

    snap_thread = threading.Thread(target=snapshot, daemon=True)
    snap_thread.start()
    print("Snapshot thread started – infinite loop (Ctrl+C to stop)")
    while True:
        time.sleep(1)

if __name__ == '__main__':
    start_snapshot()