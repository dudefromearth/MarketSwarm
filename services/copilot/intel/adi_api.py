"""
ADI API Routes - HTTP endpoints for AI Data Interface.

Endpoints:
- GET /api/adi/snapshot - Full ADI snapshot
- GET /api/adi/snapshot?format=csv - CSV format
- GET /api/adi/snapshot?format=text - Plain text format
- GET /api/adi/gamma - Gamma structure only
- GET /api/adi/mel - MEL scores only
- GET /api/adi/schema - Schema definition
- GET /api/adi/history - Historical snapshots
"""

import logging
from typing import Optional
from datetime import datetime

from aiohttp import web

from .adi import ADIOrchestrator
from .adi_models import AIStructureSnapshot, SCHEMA_VERSION
from .adi_exporters import get_exporter, JSONExporter, CSVExporter, TextExporter


class ADIAPIHandler:
    """
    HTTP handlers for ADI API.

    Thin layer that delegates to ADIOrchestrator.
    """

    def __init__(
        self,
        orchestrator: ADIOrchestrator,
        logger: Optional[logging.Logger] = None,
    ):
        self.adi = orchestrator
        self.logger = logger or logging.getLogger("ADI-API")

    def register_routes(self, app: web.Application) -> None:
        """Register all ADI routes on the application."""
        app.router.add_get("/api/adi/snapshot", self.get_snapshot)
        app.router.add_get("/api/adi/gamma", self.get_gamma)
        app.router.add_get("/api/adi/mel", self.get_mel)
        app.router.add_get("/api/adi/price", self.get_price)
        app.router.add_get("/api/adi/auction", self.get_auction)
        app.router.add_get("/api/adi/schema", self.get_schema)
        app.router.add_get("/api/adi/history", self.get_history)

    async def get_snapshot(self, request: web.Request) -> web.Response:
        """
        GET /api/adi/snapshot - Full ADI snapshot.

        Query params:
        - format: json (default), csv, text
        - include_user_context: true/false
        """
        format_type = request.query.get("format", "json").lower()
        include_user = request.query.get("include_user_context", "false").lower() == "true"

        # Generate fresh snapshot
        snapshot = self.adi.generate_snapshot(include_user_context=include_user)

        # Export in requested format
        exporter = get_exporter(format_type)
        content = exporter.export(snapshot)

        # Set appropriate content type
        content_types = {
            "json": "application/json",
            "csv": "text/csv",
            "text": "text/plain",
        }
        content_type = content_types.get(format_type, "application/json")

        return web.Response(
            text=content,
            content_type=content_type,
            headers={
                "X-ADI-Schema-Version": SCHEMA_VERSION,
                "X-ADI-Snapshot-ID": snapshot.snapshot_id,
            }
        )

    async def get_gamma(self, request: web.Request) -> web.Response:
        """GET /api/adi/gamma - Gamma structure only."""
        snapshot = self.adi.generate_snapshot()

        return web.json_response({
            "timestamp_utc": snapshot.timestamp_utc.isoformat(),
            "symbol": snapshot.symbol,
            "gamma_structure": snapshot.gamma_structure.to_dict(),
            "mel_gamma_effectiveness": snapshot.mel_scores.gamma_effectiveness,
            "mel_gamma_state": snapshot.mel_scores.gamma_state,
        })

    async def get_mel(self, request: web.Request) -> web.Response:
        """GET /api/adi/mel - MEL scores only."""
        snapshot = self.adi.generate_snapshot()

        return web.json_response({
            "timestamp_utc": snapshot.timestamp_utc.isoformat(),
            "mel_scores": snapshot.mel_scores.to_dict(),
        })

    async def get_price(self, request: web.Request) -> web.Response:
        """GET /api/adi/price - Price state only."""
        snapshot = self.adi.generate_snapshot()

        return web.json_response({
            "timestamp_utc": snapshot.timestamp_utc.isoformat(),
            "symbol": snapshot.symbol,
            "session": snapshot.session,
            "price_state": snapshot.price_state.to_dict(),
        })

    async def get_auction(self, request: web.Request) -> web.Response:
        """GET /api/adi/auction - Auction structure only."""
        snapshot = self.adi.generate_snapshot()

        return web.json_response({
            "timestamp_utc": snapshot.timestamp_utc.isoformat(),
            "symbol": snapshot.symbol,
            "auction_structure": snapshot.auction_structure.to_dict(),
            "mel_vp_effectiveness": snapshot.mel_scores.volume_profile_effectiveness,
            "mel_vp_state": snapshot.mel_scores.volume_profile_state,
        })

    async def get_schema(self, request: web.Request) -> web.Response:
        """GET /api/adi/schema - Schema definition."""
        schema = {
            "version": SCHEMA_VERSION,
            "description": "AI Structure Snapshot - Canonical market state for AI assistants",
            "sections": {
                "metadata": {
                    "description": "Snapshot identification and context",
                    "fields": ["timestamp_utc", "symbol", "session", "dte", "event_flags", "schema_version", "snapshot_id"],
                },
                "price_state": {
                    "description": "Current price and session metrics",
                    "fields": ["spot_price", "session_high", "session_low", "vwap", "distance_from_vwap", "intraday_range", "realized_vol_intra"],
                },
                "volatility_state": {
                    "description": "Implied and realized volatility metrics",
                    "fields": ["call_iv_atm", "put_iv_atm", "iv_skew", "iv_rv_ratio", "vol_regime"],
                },
                "gamma_structure": {
                    "description": "Dealer gamma and GEX metrics",
                    "fields": ["net_gex", "zero_gamma_level", "active_gamma_magnet", "gex_ratio", "high_gamma_strikes", "gamma_flip_level"],
                },
                "auction_structure": {
                    "description": "Volume profile and auction metrics",
                    "fields": ["poc", "value_area_high", "value_area_low", "rotation_state", "auction_state", "hvns", "lvns"],
                },
                "microstructure": {
                    "description": "Order flow and liquidity metrics",
                    "fields": ["bid_ask_imbalance", "aggressive_flow", "absorption_detected", "sweep_detected", "liquidity_state"],
                },
                "session_context": {
                    "description": "Time and session context",
                    "fields": ["minutes_since_open", "minutes_to_close", "session_phase", "is_rth", "day_of_week"],
                },
                "mel_scores": {
                    "description": "Model Effectiveness Layer scores",
                    "fields": [
                        "gamma_effectiveness", "gamma_state",
                        "volume_profile_effectiveness", "volume_profile_state",
                        "liquidity_effectiveness", "liquidity_state",
                        "volatility_effectiveness", "volatility_state",
                        "session_effectiveness", "session_state",
                        "global_structure_integrity", "coherence_state"
                    ],
                },
                "delta": {
                    "description": "Changes from previous snapshot",
                    "fields": ["spot_price", "net_gex", "zero_gamma", "global_integrity"],
                },
                "user_context": {
                    "description": "Optional user-specific context (when requested)",
                    "fields": ["selected_tile", "risk_graph_strategies", "active_alerts", "open_trades", "active_log_id"],
                },
            },
            "export_formats": ["json", "csv", "text"],
            "mel_states": {
                "VALID": "Model effectiveness >= 70%, reliable",
                "DEGRADED": "Model effectiveness 50-69%, use with caution",
                "REVOKED": "Model effectiveness < 50%, do not trust",
            },
            "coherence_states": {
                "STABLE": "Models agree, signals reinforce",
                "MIXED": "Some disagreement, selective trust",
                "COLLAPSING": "Models contradict, no clear signal",
                "RECOVERED": "Previously collapsing, now stabilizing",
            },
        }

        return web.json_response(schema)

    async def get_history(self, request: web.Request) -> web.Response:
        """GET /api/adi/history - Historical snapshots."""
        format_type = request.query.get("format", "json").lower()
        limit = int(request.query.get("limit", "100"))
        since = request.query.get("since")

        since_dt = None
        if since:
            try:
                since_dt = datetime.fromisoformat(since)
            except ValueError:
                return web.json_response({"error": "Invalid since format"}, status=400)

        history = self.adi.get_history(since=since_dt, limit=limit)

        if format_type == "csv":
            exporter = CSVExporter()
            content = exporter.export_multiple(history)
            return web.Response(
                text=content,
                content_type="text/csv",
            )
        else:
            return web.json_response({
                "count": len(history),
                "snapshots": [s.to_dict() for s in history],
            })
