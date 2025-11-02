import redis
import json
import time
import threading
import os
import signal
import sys

# Global flag for graceful exit
shutdown_flag = threading.Event()

def signal_handler(sig, frame):
    print("Shutdown signal received – graceful exit...")
    shutdown_flag.set()
    sys.exit(0)

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

def start_heartbeat():
    # Load Redis
    r = redis.Redis.from_url(os.environ.get('REDIS_MAIN_URL', 'redis://host.docker.internal:6379'))
    # Read config from truth key
    try:
        truth = json.loads(r.get('truth') or '{}')
        hb_config = truth.get('heartbeats', {}).get('common', {})
        identity = hb_config.get('id', 'massive')
        frequency = hb_config.get('frequency', 5)
    except Exception as e:
        print(f"Config error: {e} – fallback")
        identity = "massive"
        frequency = 10

    def heartbeat():
        while not shutdown_flag.is_set():
            status = "running"
            msg = json.dumps({
                "identity": identity,
                "status": status,
                "ts": time.time(),
                "container_id": os.environ.get('HOSTNAME', 'unknown')
            })
            r.publish('heartbeats', msg)
            print("Heartbeat published:", msg) # For trace
            shutdown_flag.wait(frequency)  # Sleep with flag check

        print("Heartbeat thread exiting gracefully...")

    hb_thread = threading.Thread(target=heartbeat, daemon=True)
    hb_thread.start()
    print("Thread started – infinite loop (Ctrl+C to stop)")
    try:
        while not shutdown_flag.is_set():
            time.sleep(1) # Keep alive
    except KeyboardInterrupt:
        shutdown_flag.set()
        hb_thread.join(timeout=10)  # Wait for clean exit
        print("Graceful shutdown complete.")

if __name__ == '__main__':
    start_heartbeat()