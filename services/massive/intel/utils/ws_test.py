import asyncio
import websockets
import json

API_KEY = "pdjraOWSpDbg3ER_RslZYe3dmn4Y7WCC"
WS_URL = "wss://socket.massive.com/options"

# ---- Config ----
UNDERLYING_PREFIX = "SPXW"
EXPIRY_YMD = "251208"  # 2025-12-08
LOW_STRIKE = 6840
HIGH_STRIKE = 6850
STRIKE_STEP = 5        # 5-point increments: 6840, 6845, 6850
FEED_PREFIX = "T.O"    # T.O for trades, Q.O for quotes, A.O for aggregates
# -----------------


def make_contract(expiry: str, cp: str, strike: float) -> str:
    """
    Build Massive symbol like:
      SPXW251208P06850000

    Pattern:
      UNDERLYING_PREFIX + EXPIRY_YMD + C/P + 8-digit strike * 1000
      e.g. 6850.00 -> 6,850,000 -> "06850000"
    """
    scaled = int(round(strike * 1000))  # 3 decimal places implied
    return f"{UNDERLYING_PREFIX}{expiry}{cp}{scaled:08d}"


def build_channels() -> list[str]:
    lo = min(LOW_STRIKE, HIGH_STRIKE)
    hi = max(LOW_STRIKE, HIGH_STRIKE)

    strikes = list(range(lo, hi + 1, STRIKE_STEP))
    contracts = []

    for k in strikes:
        for cp in ("C", "P"):
            contracts.append(make_contract(EXPIRY_YMD, cp, k))

    channels = [f"{FEED_PREFIX}:{c}" for c in contracts]
    print("Subscribing to channels:")
    for ch in channels:
        print("  ", ch)
    return channels


async def main():
    channels = build_channels()
    params = ",".join(channels)

    async with websockets.connect(WS_URL) as ws:
        # auth
        auth = {"action": "auth", "params": API_KEY}
        await ws.send(json.dumps(auth))
        print("sent auth")

        # subscribe to all C/P in range
        sub = {"action": "subscribe", "params": params}
        await ws.send(json.dumps(sub))
        print("sent subscribe", params)

        # stream messages
        async for msg in ws:
            print(msg)


if __name__ == "__main__":
    asyncio.run(main())