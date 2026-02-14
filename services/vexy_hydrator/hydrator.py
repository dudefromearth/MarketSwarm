"""
HydrationEngine — Builds cognition snapshots in Echo Redis.

Orchestrates the hydrate flow:
1. Check cache (snapshot exists + fresh?) → return early if valid
2. Acquire distributed lock (echo:hydrate_lock:{user_id} TTL 5s)
3. Fetch sources in parallel (per-source timeout, 2s hard ceiling)
4. Build snapshot per CognitionSnapshot schema v1
5. Enforce 256KB max (trim oldest tensions, drop low-signal)
6. Write to echo:warm_snapshot:{user_id} + meta with 30min TTL
7. Compute + return completeness score
8. Log latency metrics
"""

import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from redis import Redis

from .snapshot_schema import CognitionSnapshot, SnapshotMeta, MAX_SNAPSHOT_BYTES


SNAPSHOT_TTL = 1800  # 30 minutes
LOCK_TTL = 5         # 5 seconds


class HydrationEngine:
    """Orchestrates snapshot hydration from canonical sources."""

    def __init__(
        self,
        echo_redis: Redis,
        market_source: Any,
        warm_source: Any,
        risk_source: Any,
        system_source: Any,
        logger: Any,
    ):
        self._echo = echo_redis
        self._market = market_source
        self._warm = warm_source
        self._risk = risk_source
        self._system = system_source
        self._logger = logger

        # Metrics
        self._hydrations_total = 0
        self._hydrations_cached = 0
        self._hydrations_errors = 0
        self._avg_latency_ms = 0.0

    async def hydrate(self, user_id: int, tier: str = "observer", force: bool = False) -> Dict[str, Any]:
        """
        Hydrate cognition snapshot for a user.

        Returns:
            Dict with keys: snapshot_key, completeness, cached, latency_ms
        """
        t0 = time.time()
        snapshot_key = f"echo:warm_snapshot:{user_id}"
        meta_key = f"echo:warm_snapshot_meta:{user_id}"

        # 1. Check cache
        if not force:
            existing = self._echo.get(snapshot_key)
            if existing:
                self._hydrations_total += 1
                self._hydrations_cached += 1
                return {
                    "snapshot_key": snapshot_key,
                    "completeness": self._get_cached_completeness(meta_key),
                    "cached": True,
                    "latency_ms": int((time.time() - t0) * 1000),
                }

        # 2. Acquire distributed lock
        lock_key = f"echo:hydrate_lock:{user_id}"
        acquired = self._echo.set(lock_key, "1", ex=LOCK_TTL, nx=True)
        if not acquired:
            # Another hydration in progress — return existing or wait
            return {
                "snapshot_key": snapshot_key,
                "completeness": self._get_cached_completeness(meta_key),
                "cached": True,
                "latency_ms": int((time.time() - t0) * 1000),
                "lock_contention": True,
            }

        try:
            # 3. Fetch sources (sequential for now — Phase 3 will parallelize)
            stale_fields = []

            market_data = await self._market.fetch(timeout_ms=300)
            stale_fields.extend(market_data.get("_stale", []))

            warm_data = await self._warm.fetch(user_id, tier, timeout_ms=300)
            stale_fields.extend(warm_data.get("_stale", []))

            risk_data = await self._risk.fetch(user_id, timeout_ms=300)
            stale_fields.extend(risk_data.get("_stale", []))

            system_data = await self._system.fetch(user_id, tier, timeout_ms=300)
            stale_fields.extend(system_data.get("_stale", []))

            # 4. Build snapshot
            now = datetime.now(timezone.utc).isoformat()
            completeness = self._compute_completeness(market_data, warm_data, risk_data, system_data)

            snapshot = CognitionSnapshot(
                user_id=user_id,
                tier=tier,
                # Memory
                top_active_tensions=warm_data.get("top_active_tensions", []),
                open_threads=warm_data.get("open_threads", []),
                bias_frequency_30d=warm_data.get("bias_frequency_30d", []),
                trajectory_state=warm_data.get("trajectory_state", {}),
                # Readiness
                readiness_state=warm_data.get("readiness_profile", {}).get("state", ""),
                readiness_focus=warm_data.get("readiness_profile", {}).get("focus", ""),
                readiness_friction=warm_data.get("readiness_profile", {}).get("friction", ""),
                readiness_drift_score=warm_data.get("readiness_profile", {}).get("drift_score", 0.0),
                # Risk
                capital_snapshot=risk_data.get("capital_snapshot", {}),
                pressure_flags=risk_data.get("pressure_flags", []),
                # System
                market_regime=market_data.get("market_regime", ""),
                volatility_tag=market_data.get("volatility_tag", ""),
                system_echo_flags=system_data.get("system_echo_flags", []),
                feature_flags=system_data.get("feature_flags", []),
                # Meta
                built_at=now,
                completeness_score=completeness,
                stale_fields=stale_fields,
                sources={
                    "market": {"latency_ms": market_data.get("_latency_ms", 0)},
                    "warm": {"latency_ms": warm_data.get("_latency_ms", 0)},
                    "risk": {"latency_ms": risk_data.get("_latency_ms", 0)},
                    "system": {"latency_ms": system_data.get("_latency_ms", 0)},
                },
            )

            # 5. Serialize + enforce 256KB
            snapshot_json = snapshot.to_json()

            # 6. Write to Echo Redis with TTL
            self._echo.set(snapshot_key, snapshot_json, ex=SNAPSHOT_TTL)

            latency_ms = int((time.time() - t0) * 1000)

            meta = SnapshotMeta(
                built_at=now,
                hydration_latency_ms=latency_ms,
                completeness_score=completeness,
                stale_fields=stale_fields,
            )
            self._echo.set(meta_key, meta.to_json(), ex=SNAPSHOT_TTL)

            # 7. Metrics
            self._hydrations_total += 1
            self._avg_latency_ms = (
                (self._avg_latency_ms * (self._hydrations_total - 1) + latency_ms)
                / self._hydrations_total
            )

            self._logger.info(
                f"Hydrated snapshot for user {user_id}: "
                f"completeness={completeness:.2f} latency={latency_ms}ms "
                f"size={len(snapshot_json)}b stale={stale_fields}",
            )

            return {
                "snapshot_key": snapshot_key,
                "completeness": completeness,
                "cached": False,
                "latency_ms": latency_ms,
            }

        except Exception as e:
            self._hydrations_errors += 1
            self._logger.error(f"Hydration failed for user {user_id}: {e}")
            return {
                "snapshot_key": snapshot_key,
                "completeness": 0.0,
                "cached": False,
                "error": str(e),
                "latency_ms": int((time.time() - t0) * 1000),
            }
        finally:
            # Release lock
            try:
                self._echo.delete(lock_key)
            except Exception:
                pass

    def _compute_completeness(
        self,
        market: Dict,
        warm: Dict,
        risk: Dict,
        system: Dict,
    ) -> float:
        """Compute completeness score (0.0 - 1.0) from source data."""
        total = 4
        available = 0

        if not market.get("_stale"):
            available += 1
        elif len(market.get("_stale", [])) < 2:
            available += 0.5

        if not warm.get("_stale"):
            available += 1
        elif "warm_source_stub" in warm.get("_stale", []):
            available += 0.0  # stub = no data
        else:
            available += 0.5

        if not risk.get("_stale"):
            available += 1
        elif "risk_source_stub" in risk.get("_stale", []):
            available += 0.0
        else:
            available += 0.5

        if not system.get("_stale"):
            available += 1
        else:
            available += 0.5

        return round(available / total, 2)

    def _get_cached_completeness(self, meta_key: str) -> float:
        """Read completeness score from cached meta."""
        try:
            raw = self._echo.get(meta_key)
            if raw:
                meta = SnapshotMeta.from_json(raw)
                return meta.completeness_score
        except Exception:
            pass
        return 0.0

    def get_metrics(self) -> Dict[str, Any]:
        """Return hydration metrics."""
        return {
            "hydrations_total": self._hydrations_total,
            "hydrations_cached": self._hydrations_cached,
            "hydrations_errors": self._hydrations_errors,
            "avg_latency_ms": round(self._avg_latency_ms, 1),
            "cache_hit_rate": (
                round(self._hydrations_cached / self._hydrations_total, 2)
                if self._hydrations_total > 0 else 0.0
            ),
        }
