"""
System Source — Reads system echo flags and feature tier info.

Reads tier-gated feature flags and any system_echo patterns
(anonymized aggregate signals) for context injection.
"""

import time
from typing import Any, Dict, List


class SystemSource:
    """Reads system-level context for snapshot hydration."""

    def __init__(self, config: Dict[str, Any], logger: Any):
        self._config = config
        self._logger = logger

    async def fetch(self, user_id: int, tier: str, timeout_ms: int = 300) -> Dict[str, Any]:
        """
        Fetch system-level context (feature flags, system echo).

        Returns dict with system_echo_flags and feature_flags.
        """
        t0 = time.time()

        feature_flags = ["echo_enabled"]
        if tier in ("navigator", "coaching", "administrator"):
            feature_flags.append("deep_echo")
        if tier == "administrator":
            feature_flags.append("system_diagnostics")

        result: Dict[str, Any] = {
            "system_echo_flags": [],
            "feature_flags": feature_flags,
            "_stale": [],
        }

        # Phase 2 TODO: Read from system_echo MySQL table for aggregate patterns

        result["_latency_ms"] = int((time.time() - t0) * 1000)
        return result
