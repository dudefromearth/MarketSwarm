"""
MEL API Routes - HTTP and WebSocket endpoints for MEL service.

Endpoints:
- GET /api/mel/snapshot - Current MEL snapshot
- GET /api/mel/gamma - Gamma detail
- GET /api/mel/volume-profile - Volume profile detail
- GET /api/mel/liquidity - Liquidity detail
- GET /api/mel/volatility - Volatility detail
- GET /api/mel/session - Session detail
- GET /api/mel/history - Historical snapshots
- GET /api/mel/state - Compact state summary
- WS /ws/mel - Real-time MEL updates
"""

import asyncio
import logging
from typing import Optional, List
from datetime import datetime

from aiohttp import web

from .mel import MELOrchestrator
from .mel_models import MELSnapshot


class MELAPIHandler:
    """
    HTTP and WebSocket handlers for MEL API.

    Thin layer that delegates to MELOrchestrator.
    """

    def __init__(
        self,
        orchestrator: MELOrchestrator,
        logger: Optional[logging.Logger] = None,
        copilot_orchestrator: Optional[any] = None,
    ):
        self.mel = orchestrator
        self.logger = logger or logging.getLogger("MEL-API")
        self.ws_clients: List[web.WebSocketResponse] = []
        self.copilot = copilot_orchestrator  # For DTE control

    def register_routes(self, app: web.Application) -> None:
        """Register all MEL routes on the application."""
        app.router.add_get("/api/mel/snapshot", self.get_snapshot)
        app.router.add_get("/api/mel/gamma", self.get_gamma)
        app.router.add_get("/api/mel/volume-profile", self.get_volume_profile)
        app.router.add_get("/api/mel/liquidity", self.get_liquidity)
        app.router.add_get("/api/mel/volatility", self.get_volatility)
        app.router.add_get("/api/mel/session", self.get_session)
        app.router.add_get("/api/mel/history", self.get_history)
        app.router.add_get("/api/mel/state", self.get_state)
        app.router.add_get("/ws/mel", self.ws_handler)

    def setup_broadcast(self) -> None:
        """Subscribe to MEL updates for WebSocket broadcast."""
        self.mel.subscribe(self._on_mel_update)

    def _on_mel_update(self, snapshot: MELSnapshot) -> None:
        """Handle MEL snapshot update - broadcast to WebSocket clients."""
        if self.ws_clients:
            asyncio.create_task(self._broadcast(snapshot))

    async def _broadcast(self, snapshot: MELSnapshot) -> None:
        """Broadcast snapshot to all connected WebSocket clients."""
        data = snapshot.to_dict()

        # Include active DTE in broadcast
        if self.copilot:
            data["dte"] = self.copilot._active_dte

        for ws in list(self.ws_clients):
            try:
                await ws.send_json({"type": "mel_snapshot", "data": data})
            except Exception:
                self.ws_clients.remove(ws)

    async def close_all(self) -> None:
        """Close all WebSocket connections."""
        for ws in self.ws_clients:
            await ws.close()
        self.ws_clients.clear()

    # ========== HTTP Handlers ==========

    async def get_snapshot(self, request: web.Request) -> web.Response:
        """GET /api/mel/snapshot - Current MEL snapshot. Accepts ?dte=N query param."""
        # Parse DTE and update active DTE if changed
        dte = int(request.query.get("dte", "0"))
        if self.copilot:
            self.copilot.set_active_dte(dte)
            # Trigger immediate recalculation
            snapshot = await self.mel.calculate_snapshot()
        else:
            snapshot = self.mel.get_current_snapshot()

        if not snapshot:
            return web.json_response({"error": "No snapshot available"}, status=404)

        data = snapshot.to_dict()
        data["dte"] = dte
        return web.json_response(data)

    async def get_gamma(self, request: web.Request) -> web.Response:
        """GET /api/mel/gamma - Gamma effectiveness detail."""
        return await self._get_model_detail("gamma")

    async def get_volume_profile(self, request: web.Request) -> web.Response:
        """GET /api/mel/volume-profile - Volume profile effectiveness detail."""
        return await self._get_model_detail("volume_profile")

    async def get_liquidity(self, request: web.Request) -> web.Response:
        """GET /api/mel/liquidity - Liquidity effectiveness detail."""
        return await self._get_model_detail("liquidity")

    async def get_volatility(self, request: web.Request) -> web.Response:
        """GET /api/mel/volatility - Volatility effectiveness detail."""
        return await self._get_model_detail("volatility")

    async def get_session(self, request: web.Request) -> web.Response:
        """GET /api/mel/session - Session effectiveness detail."""
        return await self._get_model_detail("session")

    async def _get_model_detail(self, model_name: str) -> web.Response:
        """Get detail for a specific model."""
        snapshot = self.mel.get_current_snapshot()
        if not snapshot:
            return web.json_response({"error": "No snapshot available"}, status=404)

        model_map = {
            "gamma": snapshot.gamma,
            "volume_profile": snapshot.volume_profile,
            "liquidity": snapshot.liquidity,
            "volatility": snapshot.volatility,
            "session": snapshot.session_structure,
        }

        score = model_map.get(model_name)
        if not score:
            return web.json_response({"error": f"Unknown model: {model_name}"}, status=404)

        return web.json_response({
            "model": model_name,
            "timestamp": snapshot.timestamp_utc.isoformat(),
            **score.to_dict(),
        })

    async def get_history(self, request: web.Request) -> web.Response:
        """GET /api/mel/history - Historical snapshots."""
        limit = int(request.query.get("limit", "100"))
        since = request.query.get("since")

        since_dt = None
        if since:
            try:
                since_dt = datetime.fromisoformat(since)
            except ValueError:
                return web.json_response({"error": "Invalid since format"}, status=400)

        history = self.mel.get_history(since=since_dt, limit=limit)

        return web.json_response({
            "count": len(history),
            "snapshots": [s.to_dict() for s in history],
        })

    async def get_state(self, request: web.Request) -> web.Response:
        """GET /api/mel/state - Compact state summary."""
        snapshot = self.mel.get_current_snapshot()
        if not snapshot:
            return web.json_response({"error": "No snapshot available"}, status=404)

        return web.json_response({
            "summary": snapshot.get_state_summary(),
            "global_integrity": snapshot.global_structure_integrity,
            "coherence_state": snapshot.coherence_state.value,
            "structure_present": self.mel.is_structure_present(),
            "event_flags": snapshot.event_flags,
            "models": {
                "gamma": snapshot.gamma.state.value,
                "volume_profile": snapshot.volume_profile.state.value,
                "liquidity": snapshot.liquidity.state.value,
                "volatility": snapshot.volatility.state.value,
                "session": snapshot.session_structure.state.value,
            },
        })

    # ========== WebSocket Handler ==========

    async def ws_handler(self, request: web.Request) -> web.WebSocketResponse:
        """WS /ws/mel - Real-time MEL updates. Accepts ?dte=N query param."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        # Parse DTE from query param
        dte = int(request.query.get("dte", "0"))

        # Set active DTE on copilot orchestrator
        if self.copilot:
            self.copilot.set_active_dte(dte)

        self.ws_clients.append(ws)
        self.logger.info(f"MEL WebSocket client connected (DTE={dte}, {len(self.ws_clients)} total)")

        # Send current snapshot immediately
        snapshot = self.mel.get_current_snapshot()
        if snapshot:
            data = snapshot.to_dict()
            data["dte"] = dte  # Include DTE in response
            await ws.send_json({"type": "mel_snapshot", "data": data})

        try:
            async for msg in ws:
                pass  # One-way stream, clients don't send
        finally:
            self.ws_clients.remove(ws)
            self.logger.info(f"MEL WebSocket client disconnected ({len(self.ws_clients)} remaining)")

        return ws
