"""
Cognition Snapshot Schema v1 — Structured state for Vexy's reasoning.

The snapshot is the single object Vexy reads from Echo Redis to hydrate
a user's cognitive context before reasoning. Built by the hydrator,
consumed by the kernel.
"""

import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


SCHEMA_VERSION = "1.0"
MAX_SNAPSHOT_BYTES = 256 * 1024  # 256KB hard cap


@dataclass
class CognitionSnapshot:
    """Complete cognition snapshot for a single user."""

    schema_version: str = SCHEMA_VERSION

    # User identity
    user_id: int = 0
    tier: str = "observer"
    timezone: str = "America/New_York"

    # Memory (from WARM MySQL)
    top_active_tensions: List[Dict[str, Any]] = field(default_factory=list)
    open_threads: List[Dict[str, Any]] = field(default_factory=list)
    bias_frequency_30d: List[Dict[str, Any]] = field(default_factory=list)
    trajectory_state: Dict[str, Any] = field(default_factory=dict)

    # Readiness (from readiness cache or MySQL)
    readiness_state: str = ""
    readiness_focus: str = ""
    readiness_friction: str = ""
    readiness_drift_score: float = 0.0
    readiness_last_updated: str = ""

    # Risk (from journal/SSE APIs)
    capital_snapshot: Dict[str, Any] = field(default_factory=dict)
    pressure_flags: List[str] = field(default_factory=list)

    # System (from market-redis)
    market_regime: str = ""
    volatility_tag: str = ""
    system_echo_flags: List[Dict[str, Any]] = field(default_factory=list)
    feature_flags: List[str] = field(default_factory=list)

    # Meta
    built_at: str = ""
    completeness_score: float = 0.0
    stale_fields: List[str] = field(default_factory=list)
    sources: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        """Serialize to JSON, enforcing 256KB cap."""
        data = asdict(self)
        raw = json.dumps(data, separators=(",", ":"))

        if len(raw) <= MAX_SNAPSHOT_BYTES:
            return raw

        # Over budget — trim oldest tensions, then open_threads
        while len(raw) > MAX_SNAPSHOT_BYTES and data["top_active_tensions"]:
            data["top_active_tensions"].pop()
            raw = json.dumps(data, separators=(",", ":"))

        while len(raw) > MAX_SNAPSHOT_BYTES and data["open_threads"]:
            data["open_threads"].pop()
            raw = json.dumps(data, separators=(",", ":"))

        return raw

    @classmethod
    def from_json(cls, raw: str) -> "CognitionSnapshot":
        """Deserialize from JSON."""
        data = json.loads(raw)
        return cls(
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            user_id=data.get("user_id", 0),
            tier=data.get("tier", "observer"),
            timezone=data.get("timezone", "America/New_York"),
            top_active_tensions=data.get("top_active_tensions", []),
            open_threads=data.get("open_threads", []),
            bias_frequency_30d=data.get("bias_frequency_30d", []),
            trajectory_state=data.get("trajectory_state", {}),
            readiness_state=data.get("readiness_state", ""),
            readiness_focus=data.get("readiness_focus", ""),
            readiness_friction=data.get("readiness_friction", ""),
            readiness_drift_score=data.get("readiness_drift_score", 0.0),
            readiness_last_updated=data.get("readiness_last_updated", ""),
            capital_snapshot=data.get("capital_snapshot", {}),
            pressure_flags=data.get("pressure_flags", []),
            market_regime=data.get("market_regime", ""),
            volatility_tag=data.get("volatility_tag", ""),
            system_echo_flags=data.get("system_echo_flags", []),
            feature_flags=data.get("feature_flags", []),
            built_at=data.get("built_at", ""),
            completeness_score=data.get("completeness_score", 0.0),
            stale_fields=data.get("stale_fields", []),
            sources=data.get("sources", {}),
        )


@dataclass
class SnapshotMeta:
    """Lightweight metadata for a cached snapshot."""
    built_at: str = ""
    hydration_latency_ms: int = 0
    completeness_score: float = 0.0
    stale_fields: List[str] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION
    source_versions: Dict[str, str] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"))

    @classmethod
    def from_json(cls, raw: str) -> "SnapshotMeta":
        data = json.loads(raw)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
