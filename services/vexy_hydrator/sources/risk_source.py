"""
Risk Source — Reads position/capital data for risk context.

Reads from journal API or direct Redis state to build risk
portion of the cognition snapshot.
"""

import time
from typing import Any, Dict


class RiskSource:
    """Reads risk/capital state for snapshot hydration."""

    def __init__(self, config: Dict[str, Any], logger: Any):
        self._config = config
        self._logger = logger

    async def fetch(self, user_id: int, timeout_ms: int = 300) -> Dict[str, Any]:
        """
        Fetch risk/capital data for a user.

        Returns dict with capital_snapshot and pressure_flags.
        Phase 1: Returns stub data. Phase 2+ will read from journal API.
        """
        t0 = time.time()
        result: Dict[str, Any] = {
            "capital_snapshot": {},
            "pressure_flags": [],
            "_stale": ["risk_source_stub"],
        }

        # Phase 2 TODO: Call journal API /api/positions/summary for user
        # or read from Redis cached position state

        result["_latency_ms"] = int((time.time() - t0) * 1000)
        return result
