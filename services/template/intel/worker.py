import json


class Worker:
    def __init__(self, logger):
        self.logger = logger

    async def handle(self, raw_msg: str):
        try:
            data = json.loads(raw_msg)
        except Exception:
            self.logger.warn("received non-JSON message")
            return

        self.logger.debug(f"received message: {data}")