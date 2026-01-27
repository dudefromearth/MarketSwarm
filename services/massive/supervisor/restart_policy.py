import random
import time


class RestartPolicy:
    def __init__(self, config, logger):
        self.logger = logger
        self.base = int(config.get("MASSIVE_RESTART_BASE_SEC", 2))
        self.max_delay = int(config.get("MASSIVE_RESTART_MAX_SEC", 60))
        self.attempts = 0

    def reset(self):
        self.attempts = 0

    def next_delay(self) -> float:
        self.attempts += 1
        delay = min(self.base * (2 ** (self.attempts - 1)), self.max_delay)
        jitter = random.uniform(0.0, delay * 0.2)
        return delay + jitter