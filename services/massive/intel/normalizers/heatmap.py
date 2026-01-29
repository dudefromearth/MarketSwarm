# services/massive/intel/normalizers/heatmap.py

from typing import Dict, Any
import json
import re
import time


async def normalize_chain_snapshot_for_heatmap(
    *,
    redis,
    logger,
    snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Normalize a single chain contract or websocket tick into uniform format.
    Type derived from ticker — no separate option_type required.
    Fails loudly on invalid ticker format or missing required fields.
    Adds "last" field set to "mid" value for WS compatibility.
    """
    # Parse basic fields (adapt to raw Massive API structure)
    details = snapshot.get("details") or {}
    last_quote = snapshot.get("last_quote") or {}
    greeks = snapshot.get("greeks") or {}

    # Ticker is ONLY from details["ticker"] — no fallback
    ticker = details.get("ticker")
    if not ticker:
        summary = {
            "underlying": snapshot.get("underlying") or details.get("underlying"),
            "expiration": details.get("expiration_date"),
            "strike": details.get("strike_price")
        }
        error_msg = f"Missing ticker in snapshot details - failing normalization: {json.dumps(summary)}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Derive type from ticker (C/P after date)
    match = re.search(r'([CP])(\d{5,8})', ticker)
    if not match:
        summary = {
            "ticker": ticker,
            "underlying": snapshot.get("underlying") or details.get("underlying"),
            "expiration": details.get("expiration_date"),
            "strike": details.get("strike_price")
        }
        error_msg = f"Invalid ticker format (cannot parse type) - failing normalization: {json.dumps(summary)}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    type_char = match.group(1)
    contract_type = "call" if type_char == "C" else "put" if type_char == "P" else None
    if contract_type is None:
        summary = {
            "ticker": ticker,
            "type_char": type_char
        }
        error_msg = f"Invalid type character '{type_char}' in ticker - failing normalization: {json.dumps(summary)}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    expiration = details.get("expiration_date")
    if not expiration:
        summary = {
            "ticker": ticker,
            "underlying": snapshot.get("underlying") or details.get("underlying"),
            "strike": details.get("strike_price"),
            "type": contract_type
        }
        error_msg = f"Missing expiration_date - failing normalization: {json.dumps(summary)}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    strike_raw = details.get("strike_price")
    if strike_raw is None:
        summary = {
            "ticker": ticker,
            "underlying": snapshot.get("underlying") or details.get("underlying"),
            "expiration": expiration,
            "type": contract_type
        }
        error_msg = f"Missing strike_price - failing normalization: {json.dumps(summary)}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    try:
        strike = float(strike_raw)
        if strike <= 0:
            raise ValueError("Strike must be positive")
    except (TypeError, ValueError) as e:
        summary = {
            "ticker": ticker,
            "strike_raw": strike_raw,
            "underlying": snapshot.get("underlying") or details.get("underlying"),
            "expiration": expiration,
            "type": contract_type
        }
        error_msg = f"Invalid strike_price '{strike_raw}' - failing normalization: {json.dumps(summary)} ({str(e)})"
        logger.error(error_msg)
        raise ValueError(error_msg)

    mid_price = last_quote.get("mid") or last_quote.get("midpoint") or 0.0

    payload = {
        "id": ticker,  # Raw, unchanged ticker from details
        "underlying": snapshot.get("underlying") or details.get("underlying"),
        "expiration": expiration,
        "strike": strike,
        "type": contract_type,
        "bid": last_quote.get("bid"),
        "ask": last_quote.get("ask"),
        "mid": last_quote.get("mid"),
        "last": last_quote.get("mid"),  # Assign mid to last for WS compatibility
        "delta": greeks.get("delta"),
        "gamma": greeks.get("gamma"),
        "theta": greeks.get("theta"),
        "vega": greeks.get("vega"),
        "oi": snapshot.get("open_interest"),
        "ts": snapshot.get("ts") or time.time(),
        # Include full raw details for popup/metadata
        "raw_details": details,
        "raw_last_quote": last_quote,
        "raw_greeks": greeks,
    }

    return payload