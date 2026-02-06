from massive import RESTClient
from datetime import datetime, timezone

client = RESTClient("pdjraOWSpDbg3ER_RslZYe3dmn4Y7WCC")

# Use a known-valid recent timestamp
ts = datetime.now(timezone.utc)
epoch_ms = int(ts.timestamp() * 1000)

print("Timestamp:", epoch_ms)

items = client.list_snapshot_options_chain("I:SPX", params={"timestamp": epoch_ms})

count = 0
for item in items:
    count += 1
    print(item.details.ticker, item.details.strike_price)
    if count > 10:
        break

print("Count:", count)