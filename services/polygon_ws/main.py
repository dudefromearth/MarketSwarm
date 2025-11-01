import threading
import time

from heartbeat import start_heartbeat
from polygon_snap import start_snapshot

if __name__ == '__main__':
    print("Ignition: Starting heartbeat and snapshot...")
    start_heartbeat()
    start_snapshot()
    print("Threads started – infinite block (Ctrl+C to stop)")
    while True:
        time.sleep(1)