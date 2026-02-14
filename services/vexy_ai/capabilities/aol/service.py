"""
AOL Service — Admin Orchestration Layer business logic.

Provides:
- Governance parameter management (mutable config)
- Kill switch state
- Validation log access
- Health aggregation

Immutable doctrine (playbooks, terms, constraints) is read-only —
changes require version bump + service restart + deployment.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class KillSwitchState:
    """State of system-wide kill switches."""
    pde_enabled: bool = True
    overlay_enabled: bool = True
    rv_enabled: bool = True
    lpd_enabled: bool = True
    last_toggled_by: Optional[str] = None
    last_toggled_at: Optional[float] = None


@dataclass
class ValidationLogEntry:
    """A logged validation event."""
    ts: float
    user_id: int
    doctrine_mode: str
    hard_violations: List[str]
    soft_warnings: List[str]
    regenerated: bool
    domain: str


class AOLService:
    """
    Admin Orchestration Layer service.

    Manages mutable governance parameters and provides
    read-only access to immutable doctrine.
    """

    def __init__(self, config: Dict[str, Any], logger: Any):
        self._config = config
        self._logger = logger
        self._kill_switch = KillSwitchState()
        self._validation_log: List[ValidationLogEntry] = []
        self._max_log_entries = 500

        # Mutable governance parameters
        self._lpd_config = {
            "confidence_threshold": 0.6,
            "hybrid_margin": 0.3,
        }
        self._validator_config = {
            "strictness": "normal",  # "relaxed" | "normal" | "strict"
            "max_regeneration_attempts": 1,
            "log_soft_warnings": True,
        }
        self._thresholds = {
            "pde_scan_interval_sec": 900,
            "overlay_ttl_hours": 24,
            "overlay_max_per_week": 5,
            "overlay_cooldown_hours": 48,
            "overlay_min_confidence": 0.70,
        }

    @property
    def kill_switch(self) -> KillSwitchState:
        return self._kill_switch

    def toggle_kill_switch(self, subsystem: str, enabled: bool, admin_user: str = "unknown") -> bool:
        """Toggle a kill switch. Returns True if the state changed."""
        attr_map = {
            "pde": "pde_enabled",
            "overlay": "overlay_enabled",
            "rv": "rv_enabled",
            "lpd": "lpd_enabled",
        }
        attr = attr_map.get(subsystem)
        if not attr:
            return False

        old_value = getattr(self._kill_switch, attr)
        setattr(self._kill_switch, attr, enabled)
        self._kill_switch.last_toggled_by = admin_user
        self._kill_switch.last_toggled_at = time.time()

        self._logger.info(
            f"Kill switch: {subsystem} {'enabled' if enabled else 'disabled'} "
            f"by {admin_user}",
            emoji="🔴" if not enabled else "🟢",
        )
        return old_value != enabled

    def log_validation(
        self,
        user_id: int,
        doctrine_mode: str,
        hard_violations: List[str],
        soft_warnings: List[str],
        regenerated: bool,
        domain: str,
    ) -> None:
        """Log a validation event."""
        entry = ValidationLogEntry(
            ts=time.time(),
            user_id=user_id,
            doctrine_mode=doctrine_mode,
            hard_violations=hard_violations,
            soft_warnings=soft_warnings,
            regenerated=regenerated,
            domain=domain,
        )
        self._validation_log.append(entry)
        if len(self._validation_log) > self._max_log_entries:
            self._validation_log = self._validation_log[-self._max_log_entries:]

    def get_validation_log(self, limit: int = 50) -> List[Dict]:
        """Get recent validation log entries."""
        entries = self._validation_log[-limit:]
        return [
            {
                "ts": e.ts,
                "user_id": e.user_id,
                "doctrine_mode": e.doctrine_mode,
                "hard_violations": e.hard_violations,
                "soft_warnings": e.soft_warnings,
                "regenerated": e.regenerated,
                "domain": e.domain,
            }
            for e in reversed(entries)
        ]

    def get_lpd_config(self) -> Dict[str, Any]:
        return dict(self._lpd_config)

    def update_lpd_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update LPD configuration (thresholds only)."""
        allowed_keys = {"confidence_threshold", "hybrid_margin"}
        for key, val in updates.items():
            if key in allowed_keys:
                self._lpd_config[key] = val
        return self.get_lpd_config()

    def get_validator_config(self) -> Dict[str, Any]:
        return dict(self._validator_config)

    def update_validator_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update validator configuration (strictness toggles only)."""
        allowed_keys = {"strictness", "max_regeneration_attempts", "log_soft_warnings"}
        for key, val in updates.items():
            if key in allowed_keys:
                self._validator_config[key] = val
        return self.get_validator_config()

    def get_thresholds(self) -> Dict[str, Any]:
        return dict(self._thresholds)

    def update_thresholds(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update governance thresholds (PDE, overlay, cooldown)."""
        for key, val in updates.items():
            if key in self._thresholds:
                self._thresholds[key] = val
        return self.get_thresholds()
