import requests
import json  # Added this
import os

api_key = os.environ.get('POLYGON_API_KEY', 'your_key')
symbol = 'SPX'
limit = 3

url = f"https://api.polygon.io/v3/snapshot/options/{symbol}?limit={limit}&apikey={api_key}"

resp = requests.get(url)
print(f"Status: {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    print("Full Response Keys:", list(data.keys()))
    if 'results' in data:
        print(f"Total Records: {len(data['results'])}")
        for i, item in enumerate(data['results'][:3]):
            print(f"\n--- Record {i+1} ---")
            print(json.dumps(item, indent=2))  # Full record
            # Extract key fields
            details = item.get('details', {})
            strike = details.get('strike_price', None)
            type_ = details.get('contract_type', 'unknown')
            bid = item.get('bid', 0)
            ask = item.get('ask', 0)
            last = item.get('last_trade', {}).get('P', 0)
            spot = item.get('underlying_asset', {}).get('price', None)
            print(f"Strike: {strike}, Type: {type_}, Bid: {bid}, Ask: {ask}, Last: {last}, Spot: {spot}")
    else:
        print("No 'results' in response")
else:
    print("Error Response:", resp.text[:500])  # First 500 chars