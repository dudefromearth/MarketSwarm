#!/usr/bin/env python3
from datetime import datetime, timedelta, timezone
from massive import RESTClient
import pyarrow as pa
import pyarrow.parquet as pq

API_KEY = "pdjraOWSpDbg3ER_RslZYe3dmn4Y7WCC"
SYMBOL = "I:SPX"
INTERVAL_MINUTES = 5
client = RESTClient(API_KEY)

def fetch_chain_at(ts):
    epoch_ms = int(ts.timestamp() * 1000)
    try:
        return client.list_snapshot_options_chain(
            SYMBOL,
            params={"timestamp": epoch_ms}
        )
    except Exception as e:
        print(f"[ERROR] {SYMBOL} @ {ts}: {e}")
        return []

def main():
    target_day = datetime.now(timezone.utc).date() - timedelta(days=4)
    day = datetime.combine(target_day, datetime.min.time(), tzinfo=timezone.utc)
    start = day.replace(hour=9, minute=30, second=0)
    end = day.replace(hour=16, minute=0, second=0)

    rows = []
    ts = start
    print(f"\nCollecting {SYMBOL} for {target_day} in 5-minute increments...\n")

    while ts <= end:
        chain = fetch_chain_at(ts)
        for opt in chain:
            rows.append({
                "timestamp": ts.isoformat(),
                "strike": opt.details.strike_price,
                "type": opt.details.contract_type,
                "expiration": opt.details.expiration_date,
                "bid": opt.last_quote.bid,
                "ask": opt.last_quote.ask,
                "last": opt.last_trade.price if opt.last_trade else None,
                "iv": opt.implied_volatility,
                "delta": opt.greeks.delta,
                "gamma": opt.greeks.gamma,
                "theta": opt.greeks.theta,
                "vega": opt.greeks.vega,
                "volume": opt.last_trade.size if opt.last_trade else None,
                "oi": opt.open_interest,
                "underlying_price": opt.underlying_asset.price,
            })
        ts += timedelta(minutes=INTERVAL_MINUTES)

    if rows:
        table = pa.Table.from_pylist(rows)
        filename = f"SPX_intraday_{target_day}.parquet"
        pq.write_table(table, filename)
        print(f"Saved → {filename}")
    else:
        print("No data collected.")

if __name__ == "__main__":
    main()