# Save as: services/massive/utils/get_one_real_spx_snapshot_now.py

from massive import RESTClient
from datetime import datetime, timezone
import pyarrow as pa
import pyarrow.parquet as pq
import os

client = RESTClient("zqgWGLn564g9sidvCoDj4fPebmhHSTqy")
OUT_DIR = "/Users/ernie/MarketSwarm/data/massive_raw"
os.makedirs(OUT_DIR, exist_ok=True)

print("Pulling the most recent SPX options chain snapshot right now (Friday close)...")

chain = []
for option in client.list_snapshot_options_chain("I:SPX"):
    option["snapshot_timestamp"] = datetime.now(timezone.utc).isoformat()
    chain.append(option)

print(f"Got {len(chain)} contracts — saving...")

table = pa.Table.from_pylist(chain)
path = f"{OUT_DIR}/spx_snapshot_latest.parquet"
pq.write_table(table, path, compression="zstd")

print(f"DONE → {path} ({len(chain)} rows)")
print("File is real. Run this to see it:")
print(f"   ls -lh {path}")
print(f"   python3 -c \"import pandas as pd; print(pd.read_parquet('{path}')[['strike_price','bid','ask','open_interest']].head())\"")