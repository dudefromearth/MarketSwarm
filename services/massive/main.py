# ---- Massive Main ----
import os, json, time, socket, traceback
from chain_0dte import run_chain0dte

def send(sock, *parts):
    enc = [(x if isinstance(x, bytes) else str(x).encode()) for x in parts]
    buf = b"*%d\r\n" % len(enc) + b"".join([b"$%d\r\n%s\r\n" % (len(x), x) for x in enc])
    sock.sendall(buf)

def rdline(sock):
    b = b""
    while not b.endswith(b"\r\n"): b += sock.recv(1)
    return b[:-2]

if __name__ == "__main__":
    print("🧠 Starting Massive service...")

    host, port = "system-redis", 6379
    ch_chain = "sse:chain-feed"
    ch_hb = "massive:heartbeat"
    svc = "massive"

    sock = socket.create_connection((host, port))
    hb_interval = float(os.getenv("HB_INTERVAL_SEC", "5"))
    chain_interval = 60  # run every 60s

    last_chain = 0
    i = 0

    while True:
        i += 1
        try:
            # heartbeat
            send(sock, "PUBLISH", ch_hb, json.dumps({"svc": svc, "i": i, "ts": int(time.time())}))
            rdline(sock)
            print(f"beat {svc} #{i} -> {ch_hb}")

            # periodic chain fetch
            if time.time() - last_chain >= chain_interval:
                print("⛓  Fetching 0DTE chain snapshot...")
                try:
                    run_chain0dte(sock, ch_chain)
                except Exception as e:
                    print(f"❌ Chain fetch failed: {e}")
                    traceback.print_exc()
                last_chain = time.time()

        except Exception as e:
            print(f"💥 Unexpected error in main loop: {e}")
            traceback.print_exc()
            time.sleep(2)

        time.sleep(hb_interval)
# ---- end ----