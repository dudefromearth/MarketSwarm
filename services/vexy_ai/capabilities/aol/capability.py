"""
AOL Capability — Admin Orchestration Layer v2.0.

Registers doctrine governance endpoints under /api/vexy/admin/doctrine/:
- READ-ONLY: Playbook registry, canonical terms
- MUTABLE: LPD config, validator config, thresholds, kill switch
- OBSERVABILITY: Validation log, classification log, health
- PDE: Pattern detection alerts and metrics
- AOS: Active overlay management
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional

import aiohttp
from fastapi import APIRouter

from ...core.capability import BaseCapability
from .service import AOLService

# PDE scan loop constants
MAX_USERS_PER_CYCLE = 50
JOURNAL_BASE = "http://localhost:3002"


class AOLCapability(BaseCapability):
    name = "aol"
    version = "2.0.0"
    dependencies = ["chat"]  # Needs kernel to be available
    buses_required = []

    async def start(self) -> None:
        kernel = getattr(self.vexy, "kernel", None)
        if not kernel:
            self.logger.warn("AOL capability: kernel not available", emoji="⚠️")
            return

        self.service = AOLService(config=self.config, logger=self.logger)
        self._kernel = kernel

        # Initialize PDE + AOS (with Redis persistence)
        from ...doctrine.pde import PatternDetectionEngine
        from ...doctrine.aos import AdminOrchestrationService

        self._pde = PatternDetectionEngine(logger=self.logger)

        # Create sync Redis client for AOS write-through persistence (system-redis)
        redis_client = None
        try:
            import redis as sync_redis
            buses = self.config.get("buses", {}) or {}
            system_url = buses.get("system-redis", {}).get("url", "redis://127.0.0.1:6379")
            redis_client = sync_redis.from_url(system_url, decode_responses=True)
            redis_client.ping()
            self.logger.info("AOS: Redis persistence connected (system-redis)", emoji="🔴")
        except Exception as e:
            self.logger.warn(f"AOS: Redis persistence unavailable (in-memory only): {e}", emoji="⚠️")
            redis_client = None

        self._aos = AdminOrchestrationService(logger=self.logger, redis_client=redis_client)
        self._redis = redis_client

        # Wire Redis to playbook registry for override persistence
        if redis_client and self._kernel:
            registry = getattr(self._kernel, "playbook_registry", None)
            if registry:
                registry.set_redis(redis_client)
                self.logger.info("AOL: Redis wired to playbook registry for overrides", emoji="🔗")

        # Scan loop state
        # NOTE: Single-process assumption. Multi-instance requires Redis-based
        # distributed lock and cursor to prevent duplicate scanning/overlays.
        self._scan_cursor = 0
        self._scan_running = False

        # Scan metrics (for UI visibility)
        self._last_scan_ts: Optional[float] = None
        self._last_scan_users = 0
        self._last_scan_alerts = 0
        self._last_scan_latency_ms = 0
        self._last_scan_users_total = 0
        self._last_scan_batch_size = 0

        # Wire kill switch + AOS + LPD config to orchestrate endpoint and kernel
        self._wire_runtime_refs()

        self._started = True
        self.logger.info("AOL capability started (doctrine governance + PDE + AOS active)", emoji="🛡️")

    def _wire_runtime_refs(self) -> None:
        """Wire kill switch, AOS, and LPD config refs to orchestrate and kernel.

        The orchestrate endpoint (admin.py) and kernel (kernel.py) are created
        before capabilities start. We attach references as function/instance
        attributes so they can check kill switch state and pass LPD config
        at request time.
        """
        # Wire to orchestrate endpoint (function-level attrs on admin.py's orchestrate)
        try:
            from services.vexy_ai.adapters.http.routes.admin import create_admin_router
            # The orchestrate function is inside the router closure, but we already
            # set attrs on it via the module-level pattern. Find the orchestrate handler.
            # Since orchestrate uses hasattr() checks, we wire via the app's routes.
            app = self.vexy.app
            for route in app.routes:
                if hasattr(route, 'path') and route.path == '/api/vexy/admin/orchestrate':
                    endpoint = route.endpoint
                    endpoint._kill_switch = self.service.kill_switch
                    endpoint._aos = self._aos
                    endpoint._aol_service = self.service
                    self.logger.info("AOL: Wired kill switch + AOS to orchestrate endpoint", emoji="🔗")
                    break
        except Exception as e:
            self.logger.warn(f"AOL: Failed to wire orchestrate refs: {e}", emoji="⚠️")

        # Wire kill switch to kernel for RV enforcement
        if self._kernel:
            self._kernel._aol_service = self.service
            self.logger.info("AOL: Wired kill switch + LPD config to kernel", emoji="🔗")

    async def stop(self) -> None:
        # Clean up runtime refs
        if self._kernel and hasattr(self._kernel, '_aol_service'):
            self._kernel._aol_service = None
        self.service = None
        self._kernel = None
        self._pde = None
        self._aos = None
        self._started = False

    def get_routes(self) -> Optional[APIRouter]:
        router = APIRouter(prefix="/api/vexy/admin/doctrine", tags=["Doctrine Admin"])

        # =================================================================
        # READ-ONLY: Immutable Doctrine
        # =================================================================

        @router.get("/playbooks")
        async def list_doctrine_playbooks():
            """List all doctrine playbooks (read-only)."""
            registry = getattr(self._kernel, "playbook_registry", None)
            if not registry:
                return {"success": False, "error": "Playbook registry not available"}

            playbooks = []
            for domain, pb in registry._playbooks.items():
                playbooks.append({
                    "domain": pb.domain,
                    "version": pb.version,
                    "doctrine_source": pb.doctrine_source,
                    "path_runtime_version": pb.path_runtime_version,
                    "path_runtime_hash": pb.path_runtime_hash[:16] + "...",
                    "generated_at": pb.generated_at,
                    "term_count": len(pb.canonical_terminology),
                    "constraint_count": len(pb.constraints),
                })

            return {
                "success": True,
                "count": len(playbooks),
                "synchronized": registry.is_synchronized(),
                "safe_mode": registry._safe_mode,
                "playbooks": playbooks,
            }

        @router.get("/playbooks/{domain}")
        async def get_doctrine_playbook(domain: str):
            """View a specific doctrine playbook (read-only)."""
            registry = getattr(self._kernel, "playbook_registry", None)
            if not registry:
                return {"success": False, "error": "Playbook registry not available"}

            pb = registry.get_playbook(domain)
            if not pb:
                return {"success": False, "error": f"Playbook '{domain}' not found"}

            return {
                "success": True,
                "playbook": {
                    "domain": pb.domain,
                    "version": pb.version,
                    "doctrine_source": pb.doctrine_source,
                    "path_runtime_version": pb.path_runtime_version,
                    "path_runtime_hash": pb.path_runtime_hash,
                    "generated_at": pb.generated_at,
                    "canonical_terminology": pb.canonical_terminology,
                    "definitions": pb.definitions,
                    "structural_logic": pb.structural_logic,
                    "mechanisms": pb.mechanisms,
                    "constraints": pb.constraints,
                    "failure_modes": pb.failure_modes,
                    "non_capabilities": pb.non_capabilities,
                },
            }

        # =================================================================
        # PLAYBOOK EDITOR: Full Content + CRUD
        # =================================================================

        @router.get("/playbooks/{domain}/full")
        async def get_playbook_full(domain: str):
            """Full playbook content with source annotations."""
            registry = getattr(self._kernel, "playbook_registry", None)
            if not registry:
                return {"success": False, "error": "Playbook registry not available"}

            content = registry.get_full_content(domain)
            if not content:
                return {"success": False, "error": f"Playbook '{domain}' not found"}

            return {"success": True, "playbook": content}

        @router.put("/playbooks/{domain}/terms")
        async def update_playbook_terms(domain: str, body: dict):
            """Add/edit/remove canonical terms for a domain."""
            registry = getattr(self._kernel, "playbook_registry", None)
            if not registry:
                return {"success": False, "error": "Playbook registry not available"}

            ok = registry.save_override(domain, "canonical_terminology", body)
            if not ok:
                return {"success": False, "error": "Failed to save override (Redis unavailable?)"}
            return {"success": True}

        @router.put("/playbooks/{domain}/constraints")
        async def update_playbook_constraints(domain: str, body: dict):
            """Add/remove constraints for a domain."""
            registry = getattr(self._kernel, "playbook_registry", None)
            if not registry:
                return {"success": False, "error": "Playbook registry not available"}
            ok = registry.save_override(domain, "constraints", body)
            return {"success": ok, "error": None if ok else "Failed to save"}

        @router.put("/playbooks/{domain}/definitions")
        async def update_playbook_definitions(domain: str, body: dict):
            """Edit definitions dict for a domain."""
            registry = getattr(self._kernel, "playbook_registry", None)
            if not registry:
                return {"success": False, "error": "Playbook registry not available"}
            ok = registry.save_override(domain, "definitions", body)
            return {"success": ok, "error": None if ok else "Failed to save"}

        @router.put("/playbooks/{domain}/failure-modes")
        async def update_playbook_failure_modes(domain: str, body: dict):
            """Add/remove failure modes for a domain."""
            registry = getattr(self._kernel, "playbook_registry", None)
            if not registry:
                return {"success": False, "error": "Playbook registry not available"}
            ok = registry.save_override(domain, "failure_modes", body)
            return {"success": ok, "error": None if ok else "Failed to save"}

        @router.put("/playbooks/{domain}/non-capabilities")
        async def update_playbook_non_capabilities(domain: str, body: dict):
            """Add/remove non-capabilities for a domain."""
            registry = getattr(self._kernel, "playbook_registry", None)
            if not registry:
                return {"success": False, "error": "Playbook registry not available"}
            ok = registry.save_override(domain, "non_capabilities", body)
            return {"success": ok, "error": None if ok else "Failed to save"}

        @router.put("/playbooks/{domain}/structural-logic")
        async def update_playbook_structural_logic(domain: str, body: dict):
            """Add/remove structural logic for a domain."""
            registry = getattr(self._kernel, "playbook_registry", None)
            if not registry:
                return {"success": False, "error": "Playbook registry not available"}
            ok = registry.save_override(domain, "structural_logic", body)
            return {"success": ok, "error": None if ok else "Failed to save"}

        @router.put("/playbooks/{domain}/mechanisms")
        async def update_playbook_mechanisms(domain: str, body: dict):
            """Add/remove mechanisms for a domain."""
            registry = getattr(self._kernel, "playbook_registry", None)
            if not registry:
                return {"success": False, "error": "Playbook registry not available"}
            ok = registry.save_override(domain, "mechanisms", body)
            return {"success": ok, "error": None if ok else "Failed to save"}

        @router.delete("/playbooks/{domain}/overrides")
        async def clear_playbook_overrides(domain: str):
            """Clear all Redis overrides for domain, revert to base YAML."""
            registry = getattr(self._kernel, "playbook_registry", None)
            if not registry:
                return {"success": False, "error": "Playbook registry not available"}
            ok = registry.clear_overrides(domain)
            return {"success": ok}

        @router.post("/playbooks/regenerate")
        async def regenerate_playbooks():
            """Regenerate all playbooks from PathRuntime."""
            from services.vexy_ai.doctrine.playbook_generator import PlaybookGenerator
            result = PlaybookGenerator.regenerate_from_runtime()
            if result["success"]:
                # Reload registry
                registry = getattr(self._kernel, "playbook_registry", None)
                if registry:
                    registry.load_all()
            return result

        @router.get("/playbooks/diff/{domain}")
        async def get_playbook_diff(domain: str):
            """Show what admin has changed vs base YAML."""
            registry = getattr(self._kernel, "playbook_registry", None)
            if not registry:
                return {"success": False, "error": "Playbook registry not available"}
            diff = registry.get_diff(domain)
            if not diff:
                return {"success": False, "error": f"Playbook '{domain}' not found"}
            return {"success": True, "diff": diff}

        # =================================================================
        # ROUTING: Classification Router + Test Console (Phase 2)
        # =================================================================

        @router.get("/routing/map")
        async def get_routing_map():
            """Full routing map: domain -> patterns -> playbook."""
            from services.vexy_ai.doctrine.lpd import LanguagePatternDetector
            lpd = LanguagePatternDetector(redis_client=self._redis)
            return {"success": True, "routing": lpd.get_routing_map()}

        @router.put("/routing/{domain}/patterns")
        async def update_routing_patterns(domain: str, body: dict):
            """Add/remove classification patterns for a domain."""
            from services.vexy_ai.doctrine.lpd import LanguagePatternDetector
            lpd = LanguagePatternDetector(redis_client=self._redis)

            current = []
            if self._redis:
                import json as _json
                raw = self._redis.get(f"doctrine:lpd_patterns:{domain}")
                if raw:
                    current = _json.loads(raw)

            if "add" in body:
                current.extend(body["add"])
            if "remove" in body:
                for idx in sorted(body["remove"], reverse=True):
                    if 0 <= idx < len(current):
                        current.pop(idx)

            ok = lpd.save_admin_patterns(domain, current)
            return {"success": ok}

        @router.put("/routing/playbook-map")
        async def update_playbook_map(body: dict):
            """Change which playbook a domain maps to."""
            from services.vexy_ai.doctrine.lpd import LanguagePatternDetector
            lpd = LanguagePatternDetector(redis_client=self._redis)
            domain = body.get("domain", "")
            playbook = body.get("playbook", "")
            ok = lpd.save_playbook_map_override(domain, playbook)
            return {"success": ok}

        @router.post("/routing/test")
        async def test_classification(body: dict):
            """Classify a query without affecting logs/metrics (dry-run)."""
            from services.vexy_ai.doctrine.lpd import LanguagePatternDetector
            from services.vexy_ai.doctrine.dcl import DoctrineControlLayer

            message = body.get("message", "")
            if not message:
                return {"success": False, "error": "message is required"}

            lpd_config = self.service.get_lpd_config() if self.service else {}
            lpd = LanguagePatternDetector(
                confidence_threshold=lpd_config.get("confidence_threshold"),
                hybrid_margin=lpd_config.get("hybrid_margin"),
                redis_client=self._redis,
            )
            classification = lpd.classify(message)

            dcl = DoctrineControlLayer()
            mode = dcl.determine_mode(classification)
            constraints = dcl.get_constraints(mode)

            return {
                "success": True,
                "result": {
                    "domain": classification.domain.value,
                    "confidence": classification.confidence,
                    "secondary_domain": (
                        classification.secondary_domain.value
                        if classification.secondary_domain else None
                    ),
                    "doctrine_mode": mode,
                    "playbook_domain": classification.playbook_domain,
                    "matched_patterns": classification.matched_patterns[:10],
                    "require_playbook": constraints.get("require_playbook", False),
                },
            }

        # =================================================================
        # TERM REGISTRY: Cross-Playbook Mapping (Phase 3)
        # =================================================================

        @router.get("/terms/registry")
        async def get_term_registry():
            """All canonical terms across all playbooks with assignments."""
            registry = getattr(self._kernel, "playbook_registry", None)
            if not registry:
                return {"success": False, "error": "Playbook registry not available"}
            terms = registry.get_term_registry()
            return {"success": True, "terms": terms, "count": len(terms)}

        @router.post("/terms")
        async def create_term(body: dict):
            """Create new term, assign to playbooks."""
            registry = getattr(self._kernel, "playbook_registry", None)
            if not registry:
                return {"success": False, "error": "Playbook registry not available"}
            term = body.get("term", "")
            definition = body.get("definition", "")
            playbooks = body.get("playbooks", [])
            if not term or not definition or not playbooks:
                return {"success": False, "error": "term, definition, playbooks required"}
            ok = registry.add_term_to_playbooks(term, definition, playbooks)
            return {"success": ok}

        @router.put("/terms/{term}")
        async def update_term(term: str, body: dict):
            """Update term definition and playbook assignments."""
            registry = getattr(self._kernel, "playbook_registry", None)
            if not registry:
                return {"success": False, "error": "Playbook registry not available"}
            definition = body.get("definition", "")
            playbooks = body.get("playbooks", [])
            if not definition or not playbooks:
                return {"success": False, "error": "definition, playbooks required"}
            ok = registry.update_term(term, definition, playbooks)
            return {"success": ok}

        @router.delete("/terms/{term}")
        async def delete_term(term: str):
            """Remove a term from all playbooks."""
            registry = getattr(self._kernel, "playbook_registry", None)
            if not registry:
                return {"success": False, "error": "Playbook registry not available"}
            ok = registry.remove_term_from_all(term)
            return {"success": ok}

        @router.get("/terms")
        async def get_canonical_terms():
            """Get canonical term dictionary (read-only)."""
            registry = getattr(self._kernel, "playbook_registry", None)
            if not registry:
                return {"success": False, "error": "Playbook registry not available"}

            return {
                "success": True,
                "terms": registry.get_all_canonical_terms(),
                "count": len(registry.get_all_canonical_terms()),
            }

        # =================================================================
        # MUTABLE: Governance Config
        # =================================================================

        @router.get("/lpd/config")
        async def get_lpd_config():
            """Get LPD classification thresholds."""
            return {"success": True, "config": self.service.get_lpd_config()}

        @router.patch("/lpd/config")
        async def update_lpd_config(updates: dict):
            """Update LPD classification thresholds."""
            result = self.service.update_lpd_config(updates)
            return {"success": True, "config": result}

        @router.get("/validator/config")
        async def get_validator_config():
            """Get validator configuration."""
            return {"success": True, "config": self.service.get_validator_config()}

        @router.patch("/validator/config")
        async def update_validator_config(updates: dict):
            """Update validator strictness toggles."""
            result = self.service.update_validator_config(updates)
            return {"success": True, "config": result}

        @router.get("/thresholds")
        async def get_thresholds():
            """Get governance thresholds (PDE, overlay, cooldown)."""
            return {"success": True, "thresholds": self.service.get_thresholds()}

        @router.patch("/thresholds")
        async def update_thresholds(updates: dict):
            """Update governance thresholds."""
            result = self.service.update_thresholds(updates)
            return {"success": True, "thresholds": result}

        # =================================================================
        # KILL SWITCH
        # =================================================================

        @router.get("/kill-switch")
        async def get_kill_switch():
            """Get kill switch state."""
            ks = self.service.kill_switch
            return {
                "success": True,
                "kill_switch": {
                    "pde_enabled": ks.pde_enabled,
                    "overlay_enabled": ks.overlay_enabled,
                    "rv_enabled": ks.rv_enabled,
                    "lpd_enabled": ks.lpd_enabled,
                    "last_toggled_by": ks.last_toggled_by,
                    "last_toggled_at": ks.last_toggled_at,
                },
            }

        @router.post("/kill-switch")
        async def toggle_kill_switch(body: dict):
            """Toggle a subsystem kill switch."""
            subsystem = body.get("subsystem", "")
            enabled = body.get("enabled", True)
            admin_user = body.get("admin_user", "unknown")

            changed = self.service.toggle_kill_switch(subsystem, enabled, admin_user)
            return {
                "success": True,
                "changed": changed,
                "subsystem": subsystem,
                "enabled": enabled,
            }

        # =================================================================
        # OBSERVABILITY
        # =================================================================

        @router.get("/validation-log")
        async def get_validation_log(limit: int = 50):
            """Get recent validation log entries."""
            return {
                "success": True,
                "entries": self.service.get_validation_log(limit),
            }

        @router.get("/health")
        async def get_doctrine_health():
            """Get all doctrine subsystem statuses."""
            registry = getattr(self._kernel, "playbook_registry", None)
            ks = self.service.kill_switch

            registry_health = {}
            if registry:
                registry_health = registry.get_health()

            pde_status = self._pde.health.get_status() if self._pde else {}
            aos_stats = self._aos.get_stats() if self._aos else {}

            return {
                "success": True,
                "health": {
                    "registry": registry_health,
                    "kill_switch": {
                        "pde_enabled": ks.pde_enabled,
                        "overlay_enabled": ks.overlay_enabled,
                        "rv_enabled": ks.rv_enabled,
                        "lpd_enabled": ks.lpd_enabled,
                    },
                    "governance": {
                        "lpd_config": self.service.get_lpd_config(),
                        "validator_config": self.service.get_validator_config(),
                        "thresholds": self.service.get_thresholds(),
                    },
                    "pde": {
                        "status": "disabled" if pde_status.get("auto_disabled") else "active",
                        "auto_disabled": pde_status.get("auto_disabled", False),
                        "auto_disable_reason": pde_status.get("auto_disable_reason"),
                        "total_scans": pde_status.get("total_scans", 0),
                        "total_failures": pde_status.get("total_failures", 0),
                    },
                    "aos": {
                        "status": "active",
                        "active_overlays": aos_stats.get("active_overlays", 0),
                        "suppressed_users": aos_stats.get("suppressed_users", 0),
                    },
                },
            }

        # =================================================================
        # PDE: Pattern Detection
        # =================================================================

        @router.get("/patterns/active")
        async def get_active_patterns():
            """Get recent PDE pattern alerts."""
            if not self._pde:
                return {"success": False, "error": "PDE not available"}

            return {
                "success": True,
                "patterns": self._pde.get_recent_alerts(50),
                "health": self._pde.health.get_status(),
            }

        @router.get("/patterns/metrics")
        async def get_pattern_metrics():
            """Get PDE health metrics and scan loop status."""
            if not self._pde:
                return {"success": False, "error": "PDE not available"}

            return {
                "success": True,
                "metrics": self._pde.health.get_status(),
                "scan": {
                    "last_scan_ts": self._last_scan_ts,
                    "last_scan_users": self._last_scan_users,
                    "last_scan_alerts": self._last_scan_alerts,
                    "last_scan_latency_ms": self._last_scan_latency_ms,
                    "last_scan_users_total": self._last_scan_users_total,
                    "last_scan_batch_size": self._last_scan_batch_size,
                    "scan_running": self._scan_running,
                    "scan_cursor": self._scan_cursor,
                },
            }

        # =================================================================
        # AOS: Overlay Management
        # =================================================================

        @router.get("/overlays/active")
        async def get_active_overlays():
            """Get all active admin overlays."""
            if not self._aos:
                return {"success": False, "error": "AOS not available"}

            return {
                "success": True,
                "overlays": self._aos.get_all_active_overlays(),
                "stats": self._aos.get_stats(),
            }

        @router.delete("/overlays/{user_id}")
        async def suppress_user_overlay(user_id: int):
            """Suppress overlays for a specific user."""
            if not self._aos:
                return {"success": False, "error": "AOS not available"}

            self._aos.suppress_user(user_id)
            return {"success": True, "message": f"Overlays suppressed for user {user_id}"}

        return router

    def get_background_tasks(self):
        return [self._pde_scan_loop]

    # =================================================================
    # PDE Scan Loop + Data Fetching
    # =================================================================

    async def _fetch_active_users(self, days: int = 30) -> List[int]:
        """Fetch user IDs with recent Edge Lab activity from Journal."""
        url = f"{JOURNAL_BASE}/api/edge-lab/active-users"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params={"days": str(days)}) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("success"):
                            return data.get("user_ids", [])
                    return []
        except Exception as e:
            self.logger.warning(f"PDE: failed to fetch active users: {e}")
            return []

    async def _fetch_user_trades(self, user_id: int) -> List[Dict[str, Any]]:
        """Fetch Edge Lab setups + outcomes for a user, mapped to PDE trade format.

        Uses X-Internal-User-Id header (internal service auth, localhost only).
        """
        trades: List[Dict[str, Any]] = []
        headers = {"X-Internal-User-Id": str(user_id), "Content-Type": "application/json"}

        try:
            async with aiohttp.ClientSession() as session:
                # Fetch setups
                async with session.get(
                    f"{JOURNAL_BASE}/api/edge-lab/setups",
                    headers=headers,
                    params={"limit": "50"},
                ) as resp:
                    if resp.status != 200:
                        return []
                    result = await resp.json()
                    if not result.get("success"):
                        return []
                    setups = result.get("data", [])

                # For each setup, fetch outcome
                for setup in setups:
                    setup_id = setup.get("id")
                    if not setup_id:
                        continue

                    async with session.get(
                        f"{JOURNAL_BASE}/api/edge-lab/setups/{setup_id}/outcome",
                        headers=headers,
                    ) as oresp:
                        if oresp.status != 200:
                            continue
                        oresult = await oresp.json()
                        if not oresult.get("success"):
                            continue
                        outcome = oresult.get("data")
                        if not outcome:
                            continue

                    # Only include setups with confirmed outcomes and P&L
                    if not outcome.get("isConfirmed"):
                        continue
                    pnl = outcome.get("pnlResult") or outcome.get("pnl_result")
                    if pnl is None:
                        continue

                    # Map directional_bias to side
                    bias = (setup.get("directionalBias") or setup.get("directional_bias") or "").lower()
                    side = "call" if bias in ("bullish", "call", "long") else "put" if bias in ("bearish", "put", "short") else bias

                    trades.append({
                        "status": "closed",
                        "pnl": pnl,
                        "side": side,
                        "entry_time": setup.get("setupDate") or setup.get("setup_date"),
                        "exit_time": outcome.get("createdAt") or outcome.get("created_at"),
                        "strategy": setup.get("positionStructure") or setup.get("position_structure"),
                        "regime": setup.get("regime"),
                        "edge_score": None,  # Aggregated metric, dormant
                    })

        except Exception as e:
            self.logger.warning(f"PDE: failed to fetch trades for user {user_id}: {e}")

        return trades

    async def _pde_scan_loop(self):
        """Background task: PDE scan loop.

        Scans eligible users for behavioral drift patterns.
        Interval configurable via governance thresholds.
        Auto-disables on repeated failure (PDEHealthMonitor).
        """
        await asyncio.sleep(30)  # Let other services stabilize

        while True:
            try:
                ks = self.service.kill_switch

                # Check kill switch
                if not ks.pde_enabled:
                    self.logger.info("PDE scan loop paused (kill switch disabled)", emoji="⏸️")
                    await asyncio.sleep(60)
                    continue

                interval = self.service.get_thresholds().get("pde_scan_interval_sec", 900)

                # Overlap guard — skip scan if previous cycle still running
                if self._scan_running:
                    self.logger.info("PDE scan cycle still running, skipping", emoji="⏳")
                    await asyncio.sleep(interval)
                    continue

                self._scan_running = True
                t0 = time.time()
                try:
                    users = await self._fetch_active_users(days=30)
                    self._last_scan_users_total = len(users)
                    scanned = 0
                    alerts_total = 0

                    if users:
                        # Rotation: pick slice from cursor, wrap around
                        start = self._scan_cursor % len(users)
                        batch = users[start:start + MAX_USERS_PER_CYCLE]
                        if len(batch) < MAX_USERS_PER_CYCLE and start > 0:
                            batch += users[:MAX_USERS_PER_CYCLE - len(batch)]
                        self._last_scan_batch_size = len(batch)
                        self._scan_cursor = (start + len(batch)) % len(users)

                        for uid in batch:
                            try:
                                trades = await self._fetch_user_trades(uid)
                                if len(trades) < self._pde.MIN_SAMPLE_SIZE:
                                    continue
                                alerts = self._pde.scan_user(uid, trades)
                                scanned += 1
                                if alerts and ks.overlay_enabled and not self._pde.health.auto_disabled:
                                    self._aos.process_alerts(alerts, uid)
                                    alerts_total += len(alerts)
                            except Exception as e:
                                self.logger.warning(f"PDE scan error for user {uid}: {e}")
                                continue

                    latency_ms = int((time.time() - t0) * 1000)
                    self._last_scan_ts = time.time()
                    self._last_scan_users = scanned
                    self._last_scan_alerts = alerts_total
                    self._last_scan_latency_ms = latency_ms
                    self.logger.info(
                        f"PDE cycle: {scanned} users, {alerts_total} alerts, {latency_ms}ms",
                        emoji="🔍",
                    )
                finally:
                    self._scan_running = False

                # Sleep always reached — no tight-loop risk
                await asyncio.sleep(interval)

            except Exception as e:
                self.logger.warning(f"PDE scan loop error: {e}", emoji="⚠️")
                self._scan_running = False
                await asyncio.sleep(60)
