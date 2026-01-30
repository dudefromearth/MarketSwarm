"""
Commentary API - HTTP and WebSocket handlers for AI commentary.

Provides endpoints for:
- Getting recent commentary messages
- WebSocket streaming of new messages
- Configuration management
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional, Any, Set
from datetime import datetime

from .commentary import CommentaryService
from .commentary_models import CommentaryMessage, CommentaryConfig


class CommentaryAPIHandler:
    """
    HTTP and WebSocket handler for commentary service.

    Routes:
    - GET /api/commentary - Get recent messages
    - GET /api/commentary/config - Get current config
    - PUT /api/commentary/config - Update config
    - WS /ws/commentary - Stream messages
    """

    def __init__(
        self,
        service: CommentaryService,
        logger: Optional[logging.Logger] = None,
    ):
        self.service = service
        self.logger = logger or logging.getLogger("CommentaryAPI")

        # WebSocket connections
        self._ws_connections: Set[Any] = set()

        # Subscribe to messages for WebSocket broadcast
        self.service.subscribe(self._on_message)

    def _on_message(self, message: CommentaryMessage) -> None:
        """Handle new message - broadcast to WebSocket clients."""
        asyncio.create_task(self._broadcast_message(message))

    async def _broadcast_message(self, message: CommentaryMessage) -> None:
        """Broadcast message to all WebSocket clients."""
        if not self._ws_connections:
            return

        payload = {
            "type": "commentary",
            "data": message.to_dict(),
        }

        # Send to all connections
        dead_connections = []
        for ws in self._ws_connections:
            try:
                # Handle both aiohttp and raw websockets
                if hasattr(ws, 'send_json'):
                    await ws.send_json(payload)
                else:
                    await ws.send(json.dumps(payload))
            except Exception:
                dead_connections.append(ws)

        # Remove dead connections
        for ws in dead_connections:
            self._ws_connections.discard(ws)

    # ========== HTTP Handlers ==========

    async def handle_get_messages(self, request: Any) -> Dict[str, Any]:
        """
        GET /api/commentary

        Query params:
        - limit: Max messages to return (default 20)

        Returns recent commentary messages.
        """
        # Parse limit from query string
        limit = 20
        if hasattr(request, 'query'):
            limit = int(request.query.get('limit', 20))

        messages = self.service.get_messages(limit=limit)

        return {
            "messages": [m.to_dict() for m in messages],
            "count": len(messages),
            "enabled": self.service.enabled,
        }

    async def handle_get_config(self, request: Any) -> Dict[str, Any]:
        """
        GET /api/commentary/config

        Returns current commentary configuration.
        """
        config = self.service.config

        return {
            "enabled": config.enabled,
            "mode": config.mode,
            "provider": config.provider,
            "model": config.model,
            "rate_limit_per_minute": config.rate_limit_per_minute,
            "min_interval_seconds": config.min_interval_seconds,
            "debounce_seconds": config.debounce_seconds,
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
        }

    async def handle_update_config(self, request: Any) -> Dict[str, Any]:
        """
        PUT /api/commentary/config

        Body:
        - enabled: bool
        - rate_limit_per_minute: int
        - min_interval_seconds: float
        - temperature: float

        Updates commentary configuration.
        """
        body = await self._get_body(request)

        config = self.service.config

        # Update allowed fields
        if "enabled" in body:
            config.enabled = bool(body["enabled"])

        if "rate_limit_per_minute" in body:
            config.rate_limit_per_minute = int(body["rate_limit_per_minute"])

        if "min_interval_seconds" in body:
            config.min_interval_seconds = float(body["min_interval_seconds"])

        if "temperature" in body:
            config.temperature = float(body["temperature"])

        self.logger.info(f"Commentary config updated: enabled={config.enabled}")

        return {
            "status": "updated",
            "config": await self.handle_get_config(request),
        }

    async def handle_trigger_manual(self, request: Any) -> Dict[str, Any]:
        """
        POST /api/commentary/trigger

        Body:
        - type: trigger type (optional, defaults to periodic)

        Manually triggers a commentary generation.
        """
        if not self.service.enabled:
            return {
                "status": "disabled",
                "message": "Commentary is disabled",
            }

        # Create a periodic trigger to generate commentary
        from .commentary_models import CommentaryTrigger, TriggerType

        trigger = CommentaryTrigger(
            type=TriggerType.PERIODIC,
            timestamp=datetime.utcnow(),
            data={"manual": True},
            priority=5,
        )

        # Add to orchestrator queue directly
        self.service.orchestrator.trigger_detector._emit(trigger)

        return {
            "status": "triggered",
            "message": "Commentary generation triggered",
        }

    # ========== WebSocket Handler ==========

    async def handle_websocket(self, websocket: Any) -> None:
        """
        WS /ws/commentary

        Streams commentary messages to connected clients.
        """
        self._ws_connections.add(websocket)
        self.logger.info(f"Commentary WebSocket connected ({len(self._ws_connections)} total)")

        try:
            # Send current state
            await websocket.send(json.dumps({
                "type": "init",
                "data": {
                    "enabled": self.service.enabled,
                    "recent_count": len(self.service.get_messages()),
                },
            }))

            # Keep connection alive
            async for message in websocket:
                # Handle incoming messages (if any client commands needed)
                try:
                    data = json.loads(message)
                    await self._handle_ws_message(websocket, data)
                except json.JSONDecodeError:
                    pass

        except Exception as e:
            self.logger.debug(f"WebSocket error: {e}")
        finally:
            self._ws_connections.discard(websocket)
            self.logger.info(f"Commentary WebSocket disconnected ({len(self._ws_connections)} total)")

    async def _handle_ws_message(self, websocket: Any, data: Dict[str, Any]) -> None:
        """Handle incoming WebSocket message."""
        msg_type = data.get("type")

        if msg_type == "get_recent":
            # Client requesting recent messages
            limit = data.get("limit", 20)
            messages = self.service.get_messages(limit=limit)

            await websocket.send(json.dumps({
                "type": "recent",
                "data": {
                    "messages": [m.to_dict() for m in messages],
                },
            }))

        elif msg_type == "toggle":
            # Toggle enabled state
            self.service.enabled = not self.service.enabled

            await websocket.send(json.dumps({
                "type": "config_update",
                "data": {
                    "enabled": self.service.enabled,
                },
            }))

    # ========== Helpers ==========

    async def _get_body(self, request: Any) -> Dict[str, Any]:
        """Extract JSON body from request."""
        if hasattr(request, 'json'):
            return await request.json()
        return {}

    def get_routes(self) -> List[tuple]:
        """
        Get route definitions for this handler.

        Returns list of (method, path, handler) tuples.
        """
        return [
            ("GET", "/api/commentary", self.handle_get_messages),
            ("GET", "/api/commentary/config", self.handle_get_config),
            ("PUT", "/api/commentary/config", self.handle_update_config),
            ("POST", "/api/commentary/trigger", self.handle_trigger_manual),
        ]

    def get_websocket_route(self) -> tuple:
        """Get WebSocket route definition."""
        return ("/ws/commentary", self.handle_websocket)

    def register_routes(self, app: Any) -> None:
        """Register all commentary routes on an aiohttp application."""
        from aiohttp import web

        # HTTP routes
        app.router.add_get("/api/commentary", self._http_get_messages)
        app.router.add_get("/api/commentary/config", self._http_get_config)
        app.router.add_put("/api/commentary/config", self._http_update_config)
        app.router.add_post("/api/commentary/trigger", self._http_trigger)

        # WebSocket route
        app.router.add_get("/ws/commentary", self._http_ws_handler)

    async def _http_get_messages(self, request: Any) -> Any:
        """HTTP handler wrapper for get_messages."""
        from aiohttp import web
        result = await self.handle_get_messages(request)
        return web.json_response(result)

    async def _http_get_config(self, request: Any) -> Any:
        """HTTP handler wrapper for get_config."""
        from aiohttp import web
        result = await self.handle_get_config(request)
        return web.json_response(result)

    async def _http_update_config(self, request: Any) -> Any:
        """HTTP handler wrapper for update_config."""
        from aiohttp import web
        result = await self.handle_update_config(request)
        return web.json_response(result)

    async def _http_trigger(self, request: Any) -> Any:
        """HTTP handler wrapper for manual trigger."""
        from aiohttp import web
        result = await self.handle_trigger_manual(request)
        return web.json_response(result)

    async def _http_ws_handler(self, request: Any) -> Any:
        """HTTP WebSocket handler for aiohttp."""
        from aiohttp import web

        ws = web.WebSocketResponse()
        await ws.prepare(request)

        self._ws_connections.add(ws)
        self.logger.info(f"Commentary WebSocket connected ({len(self._ws_connections)} total)")

        try:
            # Send init message
            await ws.send_json({
                "type": "init",
                "data": {
                    "enabled": self.service.enabled,
                    "recent_count": len(self.service.get_messages()),
                },
            })

            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        await self._handle_ws_message_aiohttp(ws, data)
                    except json.JSONDecodeError:
                        pass
                elif msg.type == web.WSMsgType.ERROR:
                    break

        finally:
            self._ws_connections.discard(ws)
            self.logger.info(f"Commentary WebSocket disconnected ({len(self._ws_connections)} total)")

        return ws

    async def _handle_ws_message_aiohttp(self, ws: Any, data: Dict[str, Any]) -> None:
        """Handle incoming WebSocket message for aiohttp."""
        msg_type = data.get("type")

        if msg_type == "get_recent":
            limit = data.get("limit", 20)
            messages = self.service.get_messages(limit=limit)

            await ws.send_json({
                "type": "recent",
                "data": {
                    "messages": [m.to_dict() for m in messages],
                },
            })

        elif msg_type == "toggle":
            self.service.enabled = not self.service.enabled

            await ws.send_json({
                "type": "config_update",
                "data": {
                    "enabled": self.service.enabled,
                },
            })
