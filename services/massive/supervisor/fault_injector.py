import os
import threading
import time
import signal


class FaultInjector:
    def __init__(self, config, logger):
        self.logger = logger
        self.enabled = (
            str(config.get("MASSIVE_FAULT_INJECT", "false")).lower() == "true"
        )
        self.delay = int(config.get("MASSIVE_FAULT_DELAY_SEC", 10))

    def maybe_inject(self, proc):
        if not self.enabled:
            return

        def kill_later():
            time.sleep(self.delay)
            self.logger.warning(
                "[FAULT INJECTOR] simulating WS service restart",
                emoji="🧪",
            )
            proc.send_signal(signal.SIGTERM)

        threading.Thread(target=kill_later, daemon=True).start()