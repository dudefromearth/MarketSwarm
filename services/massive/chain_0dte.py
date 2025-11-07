# ---- Chain 0DTE Snapshot Fetcher ----
import os, json, time
from datetime import date
from polygon import RESTClient

def run_chain0dte(sock, ch, underlying="SPX", range_points=150):
    today = date.today().isoformat()
    api_key = os.getenv("POLYGON_API_KEY")

    if not api_key:
        print("⚠️ No POLYGON_API_KEY — skipping chain fetch.")
        return {"calls": [], "puts": []}

    client = RESTClient(api_key=api_key)

    # --- SPOT PRICE ---
    spot = 5000.0
    try:
        try:
            resp = client.get_snapshot_ticker(underlying, market="indices")
            spot = resp.day.close
        except Exception:
            resp = client.get_snapshot_ticker(underlying)
            spot = resp.day.close
    except Exception as e:
        print(f"⚠️ Spot fetch failed — using fallback: {e}")

    # --- ATM STRIKE RANGE ---
    atm = round(spot / 5) * 5
    min_strike, max_strike = atm - range_points, atm + range_points

    chain = {
        "underlying": underlying,
        "spot": float(spot),
        "atm": float(atm),
        "date": today,
        "calls": [],
        "puts": []
    }

    # --- FETCH CHAIN SNAPSHOTS ---
    for ctype in ["call", "put"]:
        try:
            results = []
            for item in client.list_snapshot_options_chain(underlying_asset=underlying):
                try:
                    strike = item.details.strike_price
                    if min_strike <= strike <= max_strike:
                        entry = {
                            "symbol": getattr(item.details, "ticker", "N/A"),
                            "strike": float(strike),
                            "bid": getattr(item.last_quote, "bid", 0.0) or 0.0,
                            "ask": getattr(item.last_quote, "ask", 0.0) or 0.0,
                            "volume": getattr(item.day, "volume", 0),
                            "oi": getattr(item, "open_interest", 0),
                            "iv": getattr(item, "implied_volatility", 0.0),
                            "greeks": {
                                k: getattr(item.greeks, k, None)
                                for k in ["delta", "gamma", "theta", "vega"]
                                if getattr(item.greeks, k, None) is not None
                            }
                        }
                        results.append(entry)
                except Exception as e:
                    print(f"  ⚠️ Skipped {ctype} contract parse: {e}")
            chain[f"{ctype}s"] = results

        except Exception as e:
            print(f"Chain fetch error for {ctype}: {e}")
            chain[f"{ctype}s"] = []

    # --- PUBLISH RESULT ---
    try:
        from main import send
        send(sock, "PUBLISH", ch, json.dumps(chain))
        print(f"✅ Published 0DTE chain ({len(chain['calls'])} calls, {len(chain['puts'])} puts) for {underlying} -> {ch}")
    except Exception as e:
        print(f"❌ Failed to publish chain: {e}")

    return chain
# ---- end ----