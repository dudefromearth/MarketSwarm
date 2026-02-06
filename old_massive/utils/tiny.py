from massive import RESTClient
from datetime import datetime, timezone, timedelta

client = RESTClient("pdjraOWSpDbg3ER_RslZYe3dmn4Y7WCC")

ts = datetime.now(timezone.utc) - timedelta(days=1)
epoch_ms = int(ts.timestamp() * 1000)

chain = client.list_snapshot_options_chain("I:SPX", params={"timestamp": epoch_ms})

for opt in chain:
    print(dir(opt))
    break

print("details:", dir(opt.details))
print("greeks:", dir(opt.greeks))
print("last_quote:", dir(opt.last_quote))
print("last_trade:", dir(opt.last_trade))
print("underlying_asset:", dir(opt.underlying_asset))