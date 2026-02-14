"""
Warm Source — Reads WARM MySQL tables for user echo data.

Phase 1: Returns empty/stub data (WARM tables not yet created).
Phase 2: Reads real user_echo, conversation_echo, user_readiness_profile.
"""

import time
from typing import Any, Dict, List, Optional


class WarmSource:
    """Reads warm-tier echo data from MySQL for snapshot hydration."""

    def __init__(self, db_config: Dict[str, Any], logger: Any):
        self._db_config = db_config
        self._logger = logger

    async def fetch(self, user_id: int, tier: str, timeout_ms: int = 300) -> Dict[str, Any]:
        """
        Fetch warm-tier data for a user.

        Phase 1: Returns stub data. Phase 2 will read real MySQL tables.

        Returns dict with tensions, threads, biases, trajectory.
        """
        t0 = time.time()
        result: Dict[str, Any] = {
            "top_active_tensions": [],
            "open_threads": [],
            "bias_frequency_30d": [],
            "trajectory_state": {},
            "readiness_profile": {},
            "_stale": ["warm_source_stub"],
        }

        # Phase 2 TODO: Read from user_echo, conversation_echo, user_readiness_profile
        # For now, return empty data — hydrator will report low completeness score

        result["_latency_ms"] = int((time.time() - t0) * 1000)
        return result
