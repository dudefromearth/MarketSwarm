# ---- Massive Main ----
import os, json, time, socket, traceback, asyncio
from chainfeed import run_chainfeed


def send(sock, *parts):
    enc = [(x if isinstance(x, bytes) else str(x).encode()) for x in parts]
    buf = b"*%d\r\n" % len(enc) + b"".join([b"$%d\r\n%s\r\n" % (len(x), x) for x in enc])
    sock.sendall(buf)


def rdline(sock):
    b = b""
    while not b.endswith(b"\r\n"):
        b += sock.recv(1)
    return b[:-2]


async def heartbeat_loop(sock, ch_hb, svc, hb_interval):
    """Sends periodic heartbeats to Redis."""
    i = 0
    while True:
        i += 1
        try:
            send(sock, "PUBLISH", ch_hb, json.dumps({"svc": svc, "i": i, "ts": int(time.time())}))
            rdline(sock)
            print(f"beat {svc} #{i} -> {ch_hb}")
        except Exception as e:
            print(f"💥 Unexpected error in heartbeat loop: {e}")
            traceback.print_exc()
            await asyncio.sleep(2)

        await asyncio.sleep(hb_interval)


async def main():
    print("🧠 Starting Massive service...")

    host, port = "system-redis", 6379
    ch_hb = "massive:heartbeat"
    svc = "massive"

    sock = socket.create_connection((host, port))
    hb_interval = float(os.getenv("HB_INTERVAL_SEC", "5"))

    # Start the heartbeat loop and chainfeed concurrently

    await asyncio.gather(
        heartbeat_loop(sock, ch_hb, svc, hb_interval),
        run_chainfeed()
    )


# ---- Massive Main ----
import asyncio
import traceback
from chainfeed import run_chainfeed

if __name__ == "__main__":
    print("⚡ Starting Massive service (ChainFeed only)...")
    try:
        asyncio.run(run_chainfeed())
    except KeyboardInterrupt:
        print("\n🛑 Massive service stopped by user.")
    except Exception as e:
        print(f"💥 Fatal error in Massive main: {e}")
        traceback.print_exc()
# ---- end ----