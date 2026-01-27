import asyncio
import subprocess
import sys
import time

from .restart_policy import RestartPolicy
from .fault_injector import FaultInjector


class MassiveSupervisor:
    def __init__(self, logger, config):
        self.logger = logger
        self.config = config
        self.policy = RestartPolicy(config, logger)
        self.faults = FaultInjector(config, logger)

    async def run(self):
        self.logger.info("[SUPERVISOR] starting", emoji="🧭")

        while True:
            try:
                await self._run_once()
                self.policy.reset()
            except Exception as e:
                self.logger.error(f"[SUPERVISOR] crash: {e}", emoji="💥")

            delay = self.policy.next_delay()
            self.logger.warning(
                f"[SUPERVISOR] restarting Massive in {delay:.1f}s",
                emoji="🔁",
            )
            await asyncio.sleep(delay)

    async def _run_once(self):
        cmd = [sys.executable, "-m", "services.massive.main"]

        self.logger.info("[SUPERVISOR] launching Massive", emoji="🚀")

        proc = subprocess.Popen(
            cmd,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )

        self.faults.maybe_inject(proc)

        exit_code = proc.wait()

        if exit_code == 0:
            self.logger.info("[SUPERVISOR] Massive exited cleanly", emoji="✅")
            return

        raise RuntimeError(f"Massive exited with code {exit_code}")