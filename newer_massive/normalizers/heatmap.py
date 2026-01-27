# services/massive/normalizers/heatmap.py

from typing import Dict, Any
import json
import re


def _parse_ws_symbol(sym: str) -> Dict[str, Any] | None:
    """
    Parse WS option symbol into components.

    Example:
      O:SPXW260107C06850000
    """
    if not sym or not sym.startswith("O:"):
        return None

    m = re.match(
        r"O:(?P<underlying>[A-Z]+)[W]?(\d{6})(?P<type>[CP])(\d{8})",
        sym,
    )
    if not m:
        return None

    raw_exp = m.group(2)  # YYMMDD
    expiration = f"20{raw_exp[0:2]}-{raw_exp[2:4]}-{raw_exp[4:6]}"

    strike = int(m.group(4)) / 1000.0

    return {
        "id": sym,
        "underlying": m.group("underlying"),
        "expiration": expiration,
        "strike": strike,
        "type": "call" if m.group("type") == "C" else "put",
    }


async def normalize_chain_snapshot_for_heatmap(
    *,
    redis,
    logger,
    epoch_id: str,
    snapshot: Dict[str, Any],
) -> None:
    """
    Normalize chain snapshot OR WS contracts into heatmap substrate.

    WRITES:
      epoch:{epoch_id}:contract:{contract_id} -> JSON STRING
    """

    pipe = redis.pipeline(transaction=False)

    # -------------------------------------------------
    # CASE 1: Chain snapshot (canonical lattice)
    # -------------------------------------------------
    if "contracts" in snapshot:
        underlying = snapshot["underlying"]
        expiration = snapshot["expiration"]
        contracts = snapshot.get("contracts", [])

        logger.info(
            f"🔥 [HEATMAP NORMALIZER] chain {underlying} {expiration} contracts={len(contracts)}"
        )

        for raw in contracts:
            details = raw.get("details") or {}
            last_quote = raw.get("last_quote") or {}
            greeks = raw.get("greeks") or {}

            contract_id = details.get("ticker")
            if not contract_id:
                continue

            key = f"epoch:{epoch_id}:contract:{contract_id}"

            # Use provider "option_type" ("C"/"P")
            option_type_raw = details.get("option_type")

            contract_type = "unknown"
            if option_type_raw == "C":
                contract_type = "call"
            elif option_type_raw == "P":
                contract_type = "put"

            # Fallback to full string if ever used
            if contract_type == "unknown":
                fallback = details.get("contract_type")
                if fallback in ("call", "put"):
                    contract_type = fallback

            payload = {
                "id": contract_id,
                "underlying": underlying,
                "expiration": expiration,
                "strike": details.get("strike_price"),
                "type": contract_type,
                "bid": last_quote.get("bid"),
                "ask": last_quote.get("ask"),
                "mid": last_quote.get("mid") or last_quote.get("midpoint"),
                "delta": greeks.get("delta"),
                "gamma": greeks.get("gamma"),
                "theta": greeks.get("theta"),
                "vega": greeks.get("vega"),
                "oi": raw.get("open_interest"),
                "ts": snapshot.get("ts"),
            }

            if contract_type == "unknown":
                logger.warning(f"[HEATMAP NORMALIZER] Unknown option_type for {contract_id}: {option_type_raw}")

            pipe.set(
                key,
                json.dumps(
                    {k: v for k, v in payload.items() if v is not None},
                    separators=(",", ":"),
                ),
            )

            pipe.expire(key, 300)

    # -------------------------------------------------
    # CASE 2: WS contract hydration (live updates)
    # -------------------------------------------------
    elif "sym" in snapshot:
        parsed = _parse_ws_symbol(snapshot["sym"])
        if not parsed:
            return

        key = f"epoch:{epoch_id}:contract:{parsed['id']}"

        payload = {
            "id": parsed["id"],
            "underlying": parsed["underlying"],
            "expiration": parsed["expiration"],
            "strike": parsed["strike"],
            "type": parsed["type"],
            "mid": snapshot.get("p"),
            "bid": snapshot.get("bp"),
            "ask": snapshot.get("ap"),
            "ts": snapshot.get("t"),
        }

        pipe.set(
            key,
            json.dumps(
                {k: v for k, v in payload.items() if v is not None},
                separators=(",", ":"),
            ),
        )

        pipe.expire(key, 300)

    await pipe.execute()