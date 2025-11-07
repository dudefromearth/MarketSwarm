# ---- Chain 0DTE Snapshot Fetcher ----
import os
import json
from datetime import date
from polygon import RESTClient

def run_chain0dte(sock, ch, underlying="SPX", range_points=150):
    today = date.today().isoformat()
    api_key = os.getenv("POLYGON_API_KEY")
    if not api_key:
        print("No POLYGON_API_KEY—skipping chain fetch")
        return

    client = RESTClient(api_key=api_key)

    # Fetch spot price (fallback for SPX index)
    try:
        # Try indices market first for SPX
        spot_resp = client.get_snapshot_ticker(underlying, market="indices")
        spot = spot_resp.day.close
    except:
        try:
            spot_resp = client.get_snapshot_ticker(underlying)
            spot = spot_resp.day.close
        except:
            spot = 5000.0  # Rough fallback for SPX ~5000
            print("Spot fetch failed—using fallback")

    # ATM strike (round to nearest 5-point tick, common for SPX)
    atm = round(spot / 5) * 5
    min_strike = atm - range_points
    max_strike = atm + range_points

    chain = {
        "underlying": underlying,
        "spot": float(spot),
        "atm": float(atm),
        "date": today,
        "calls": [],
        "puts": []
    }

    for ctype in ["call", "put"]:
        try:
            # Fetch full chain snapshot
            results = []
            for o in client.list_snapshot_options_chain(underlying_asset=underlying):
                if getattr(o.details, "expiration_date", None) == today and getattr(o.details, "contract_type", None) == ctype:
                    results.append(o)

            for r in results:
                strike = r.details.strike_price
                if min_strike <= strike <= max_strike:
                    entry = {
                        "ticker": getattr(r.details, "ticker", "UNKNOWN"),
                        "strike": float(strike),
                        "bid": float(r.last_quote.bid) if r.last_quote else 0.0,
                        "ask": float(r.last_quote.ask) if r.last_quote else 0.0,
                        "volume": int(r.day.volume) if r.day else 0,
                        "oi": int(r.open_interest) if r.open_interest else 0,
                        "iv": float(r.implied_volatility) if r.implied_volatility else 0.0,
                        "greeks": {
                            "delta": float(r.greeks.delta) if r.greeks and r.greeks.delta else None,
                            "gamma": float(r.greeks.gamma) if r.greeks and r.greeks.gamma else None,
                            "theta": float(r.greeks.theta) if r.greeks and r.greeks.theta else None,
                            "vega": float(r.greeks.vega) if r.greeks and r.greeks.vega else None,
                        }
                    }
                    entry["greeks"] = {k: v for k, v in entry["greeks"].items() if v is not None}
                    if ctype == "call":
                        chain["calls"].append(entry)
                    else:
                        chain["puts"].append(entry)

        except Exception as e:
            print(f"Chain fetch error for {ctype}: {e}")
            continue

    # Publish JSON to channel
    from main import send  # Reuse send func from main.py
    send(sock, "PUBLISH", ch, json.dumps(chain))
    print(f"Published 0DTE chain ({len(chain['calls'])} calls, {len(chain['puts'])} puts) for {underlying} -> {ch}")
# ---- end ----