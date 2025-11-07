import asyncio

class Workflow:
    def __init__(self, truth):
        self.subscriptions = ['rss:queue', 'massive:spot']

    async def start_async(self):
        """Simulated async subscriber loop."""
        while True:
            # Simulate waiting for messages
            await asyncio.sleep(5)
            print("📨 (no messages yet — still listening)")