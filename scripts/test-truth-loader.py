#!/usr/bin/env python3
import json
import socket
import sys


def load_truth():
    host = "127.0.0.1"
    port = 6379

    print(f"[test] Connecting to system-redis {host}:{port}...")

    try:
        s = socket.create_connection((host, port), timeout=2)
        print("[test] Connected.")
    except Exception as e:
        print(f"[test] ❌ Cannot connect: {e}")
        sys.exit(1)

    # Send RESP GET truth
    s.sendall(b"*2\r\n$3\r\nGET\r\n$5\r\ntruth\r\n")

    first = s.recv(1)
    if first != b"$":
        print(f"[test] ❌ Unexpected response: {first}")
        sys.exit(1)

    ln_bytes = b""
    while not ln_bytes.endswith(b"\r\n"):
        chunk = s.recv(1)
        if not chunk:
            print("[test] ❌ Failed reading length")
            sys.exit(1)
        ln_bytes += chunk

    ln = int(ln_bytes[:-2])

    if ln < 0:
        print("[test] ❌ `truth` key missing in Redis.")
        sys.exit(1)

    payload = b""
    remaining = ln + 2
    while remaining > 0:
        chunk = s.recv(remaining)
        if not chunk:
            print("[test] ❌ Incomplete read")
            sys.exit(1)
        payload += chunk
        remaining -= len(chunk)

    s.close()

    try:
        truth = json.loads(payload[:-2])
    except Exception as e:
        print(f"[test] ❌ Invalid JSON in truth: {e}")
        sys.exit(1)

    print("\n[test] ✅ Successfully loaded truth:")
    print(json.dumps(truth, indent=2))
    print()
    return truth


if __name__ == "__main__":
    load_truth()