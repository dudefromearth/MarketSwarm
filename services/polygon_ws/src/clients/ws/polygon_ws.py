import redis
import json
import time
import threading
import os
import requests
from websocket import WebSocketApp
from datetime import date

r_main = redis.Redis.from_url(os.environ.get('REDIS_MAIN_URL', 'redis://host.docker.internal:6379'))
r_market = redis.Redis.from_url(os.environ.get('REDIS_MARKET_URL', 'redis://host.docker.internal:6379'))

# Load truth
truth = json.loads(r_main.get('truth') or '{}')
config = truth.get('polygon', {})
symbols = config.get('symbols', ['SPY', 'SPX', 'QQQ', 'NDX'])
api_key = config.get('api_key', os.environ['POLYGON_API_KEY'])
strike_range = config.get('strikes_range', 60)
offset = strike_range // 2
interval = 5  # Default strike interval; make configurable later

# Get current date for 0DTE
today = date.today()
expiration = today.strftime('%y%m%d')

# Chains dict: {underlying: {strike: {"call": {price, size, bid, ask, ts}, "put": {...}}}}
chains = {sym: {} for sym in symbols}
last_pub = 0
pub_interval = 10  # Pub chain every 10s

def get_snapshot(symbol):
    url = f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers/{symbol}?apikey={api_key}"
    resp = requests.get(url)
    if resp.status_code == 200:
        data = resp.json()
        return data['results']['day']['c']  # Close price as proxy for current
    return None

def generate_symbols(symbol):
    price = get_snapshot(symbol)
    if not price:
        print(f"No price for {symbol}")
        return []
    atm = round(price / interval) * interval
    strikes = [atm + i * interval for i in range(-offset, offset + 1)]
    syms = []
    for strike in strikes:
        strike_str = f"{int(strike):08d}"
        syms.append(f"O:{symbol}{expiration}C{strike_str}")
        syms.append(f"O:{symbol}{expiration}P{strike_str}")
    return syms

# Generate all symbols
all_symbols = []
for sym in symbols:
    all_symbols.extend(generate_symbols(sym))
print(f"Subscribing to {len(all_symbols)} option contracts")

def on_message(ws, message):
    data = json.loads(message)
    sym = data.get('sym', '')
    if sym.startswith('O:'):
        # Parse symbol: O:SPY251031C00000500 -> SPY, call, 500
        parts = sym.split(':')[1]
        underlying = parts[:3]
        exp = parts[3:9]
        type_ = parts[9]
        strike_str = parts[10:]
        strike = int(strike_str)
        if underlying not in chains:
            chains[underlying] = {}
        if strike not in chains[underlying]:
            chains[underlying][strike] = {"call": {}, "put": {}}
        chain = chains[underlying][strike][type_.lower()]
        chain.update({
            'price': data.get('p', 0),
            'size': data.get('s', 0),
            'bid': data.get('b', 0),
            'ask': data.get('a', 0),
            'ts': time.time()
        })
        print(f"Updated {underlying} {strike} {type_}: price {data.get('p')}")

def on_error(ws, error):
    print(f"WS error: {error}")
    ws.close()
    time.sleep(5)
    ws.run_forever()  # Reconnect

# WS setup
ws_url = f"wss://socket.polygon.io/options?apikey={api_key}"
ws = WebSocketApp(ws_url, on_message=on_message, on_error=on_error)

# Subscribe
for sym in all_symbols:
    ws.send(json.dumps({"action": "subscribe", "params": f"T.{sym},Q.{sym}"}))  # Trades and quotes

# Timer for pub chain
def pub_chains():
    global last_pub
    while True:
        if time.time() - last_pub > pub_interval:
            for underlying, chain in chains.items():
                r_market.publish(f'options:chain:{underlying}', json.dumps(chain))
                print(f"Published chain for {underlying}")
            last_pub = time.time()
        time.sleep(1)

pub_thread = threading.Thread(target=pub_chains, daemon=True)
pub_thread.start()

# Run WS
ws.run_forever(ping_interval=30)