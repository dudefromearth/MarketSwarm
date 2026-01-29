# services/journal/intel/orchestrator.py
"""API server and main loop for the journal service."""

import asyncio
import json
from typing import Dict, Any, Optional
from datetime import datetime

from aiohttp import web

from .db import JournalDB
from .models import Trade
from .analytics import Analytics


class JournalOrchestrator:
    """REST API server for the journal service."""

    def __init__(self, config: Dict[str, Any], logger):
        self.config = config
        self.logger = logger
        self.port = int(config.get('JOURNAL_PORT', 3002))
        self.db = JournalDB()
        self.analytics = Analytics(self.db)

    def _json_response(self, data: Any, status: int = 200) -> web.Response:
        """Create a JSON response with CORS headers."""
        return web.Response(
            text=json.dumps(data, default=str),
            status=status,
            content_type='application/json',
            headers={
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type',
            }
        )

    def _error_response(self, message: str, status: int = 400) -> web.Response:
        """Create an error JSON response."""
        return self._json_response({'success': False, 'error': message}, status)

    async def handle_options(self, request: web.Request) -> web.Response:
        """Handle CORS preflight requests."""
        return web.Response(
            status=204,
            headers={
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type',
            }
        )

    async def list_trades(self, request: web.Request) -> web.Response:
        """GET /api/trades - List trades with optional filters."""
        try:
            params = request.query
            trades = self.db.list_trades(
                user_id=params.get('user_id', 'default'),
                status=params.get('status'),
                symbol=params.get('symbol'),
                strategy=params.get('strategy'),
                from_date=params.get('from'),
                to_date=params.get('to'),
                limit=int(params.get('limit', 100)),
                offset=int(params.get('offset', 0))
            )

            return self._json_response({
                'success': True,
                'data': [t.to_dict() for t in trades],
                'count': len(trades)
            })
        except Exception as e:
            self.logger.error(f"list_trades error: {e}")
            return self._error_response(str(e), 500)

    async def get_trade(self, request: web.Request) -> web.Response:
        """GET /api/trades/:id - Get a single trade."""
        try:
            trade_id = request.match_info['id']
            trade = self.db.get_trade(trade_id)

            if not trade:
                return self._error_response('Trade not found', 404)

            return self._json_response({
                'success': True,
                'data': trade.to_dict()
            })
        except Exception as e:
            self.logger.error(f"get_trade error: {e}")
            return self._error_response(str(e), 500)

    async def create_trade(self, request: web.Request) -> web.Response:
        """POST /api/trades - Create a new trade."""
        try:
            body = await request.json()

            # Generate ID if not provided
            trade_id = body.get('id') or Trade.new_id()

            # Set defaults
            entry_time = body.get('entry_time') or datetime.utcnow().isoformat()

            trade = Trade(
                id=trade_id,
                user_id=body.get('user_id', 'default'),
                symbol=body.get('symbol', 'SPX'),
                underlying=body.get('underlying', 'I:SPX'),
                strategy=body['strategy'],
                side=body['side'],
                dte=body.get('dte'),
                strike=float(body['strike']),
                width=int(body.get('width', 0)),
                quantity=int(body.get('quantity', 1)),
                entry_time=entry_time,
                entry_price=float(body['entry_price']),
                entry_spot=body.get('entry_spot'),
                max_profit=body.get('max_profit'),
                max_loss=body.get('max_loss'),
                notes=body.get('notes'),
                tags=body.get('tags', []),
                playbook_id=body.get('playbook_id'),
                source=body.get('source', 'manual')
            )

            created = self.db.create_trade(trade)
            self.logger.info(f"Created trade {created.id}: {created.strategy} {created.strike}", emoji="📝")

            return self._json_response({
                'success': True,
                'data': created.to_dict()
            }, 201)

        except KeyError as e:
            return self._error_response(f'Missing required field: {e}')
        except Exception as e:
            self.logger.error(f"create_trade error: {e}")
            return self._error_response(str(e), 500)

    async def update_trade(self, request: web.Request) -> web.Response:
        """PUT /api/trades/:id - Update a trade."""
        try:
            trade_id = request.match_info['id']
            body = await request.json()

            # Don't allow updating certain fields
            protected = ['id', 'user_id', 'created_at']
            updates = {k: v for k, v in body.items() if k not in protected}

            # Handle tags serialization
            if 'tags' in updates:
                updates['tags'] = json.dumps(updates['tags'])

            trade = self.db.update_trade(trade_id, updates)

            if not trade:
                return self._error_response('Trade not found', 404)

            return self._json_response({
                'success': True,
                'data': trade.to_dict()
            })
        except Exception as e:
            self.logger.error(f"update_trade error: {e}")
            return self._error_response(str(e), 500)

    async def delete_trade(self, request: web.Request) -> web.Response:
        """DELETE /api/trades/:id - Delete a trade."""
        try:
            trade_id = request.match_info['id']
            deleted = self.db.delete_trade(trade_id)

            if not deleted:
                return self._error_response('Trade not found', 404)

            self.logger.info(f"Deleted trade {trade_id}", emoji="🗑️")

            return self._json_response({
                'success': True,
                'message': 'Trade deleted'
            })
        except Exception as e:
            self.logger.error(f"delete_trade error: {e}")
            return self._error_response(str(e), 500)

    async def close_trade(self, request: web.Request) -> web.Response:
        """POST /api/trades/:id/close - Close a trade."""
        try:
            trade_id = request.match_info['id']
            body = await request.json()

            if 'exit_price' not in body:
                return self._error_response('exit_price is required')

            trade = self.db.close_trade(
                trade_id=trade_id,
                exit_price=float(body['exit_price']),
                exit_spot=body.get('exit_spot'),
                exit_time=body.get('exit_time')
            )

            if not trade:
                return self._error_response('Trade not found', 404)

            pnl_str = f"+${trade.pnl:.2f}" if trade.pnl and trade.pnl >= 0 else f"-${abs(trade.pnl or 0):.2f}"
            self.logger.info(f"Closed trade {trade_id}: {pnl_str}", emoji="✅")

            return self._json_response({
                'success': True,
                'data': trade.to_dict()
            })
        except Exception as e:
            self.logger.error(f"close_trade error: {e}")
            return self._error_response(str(e), 500)

    async def get_analytics(self, request: web.Request) -> web.Response:
        """GET /api/analytics - Get performance statistics."""
        try:
            params = request.query
            user_id = params.get('user_id', 'default')

            summary = self.analytics.get_summary(user_id)
            strategy_breakdown = self.analytics.get_strategy_breakdown(user_id)

            return self._json_response({
                'success': True,
                'data': {
                    'summary': summary.to_dict(),
                    'by_strategy': strategy_breakdown
                }
            })
        except Exception as e:
            self.logger.error(f"get_analytics error: {e}")
            return self._error_response(str(e), 500)

    async def get_equity_curve(self, request: web.Request) -> web.Response:
        """GET /api/analytics/equity - Get equity curve data."""
        try:
            params = request.query
            user_id = params.get('user_id', 'default')

            equity_points = self.analytics.get_equity_curve(user_id)
            daily_pnl = self.analytics.get_daily_pnl(user_id)

            return self._json_response({
                'success': True,
                'data': {
                    'equity': [p.to_dict() for p in equity_points],
                    'daily': daily_pnl
                }
            })
        except Exception as e:
            self.logger.error(f"get_equity_curve error: {e}")
            return self._error_response(str(e), 500)

    async def health_check(self, request: web.Request) -> web.Response:
        """GET /health - Health check endpoint."""
        return self._json_response({
            'success': True,
            'service': 'journal',
            'status': 'healthy',
            'ts': datetime.utcnow().isoformat()
        })

    def create_app(self) -> web.Application:
        """Create the aiohttp application with routes."""
        app = web.Application()

        # CORS preflight for all routes
        app.router.add_route('OPTIONS', '/{tail:.*}', self.handle_options)

        # Health check
        app.router.add_get('/health', self.health_check)

        # Trade CRUD
        app.router.add_get('/api/trades', self.list_trades)
        app.router.add_get('/api/trades/{id}', self.get_trade)
        app.router.add_post('/api/trades', self.create_trade)
        app.router.add_put('/api/trades/{id}', self.update_trade)
        app.router.add_delete('/api/trades/{id}', self.delete_trade)
        app.router.add_post('/api/trades/{id}/close', self.close_trade)

        # Analytics
        app.router.add_get('/api/analytics', self.get_analytics)
        app.router.add_get('/api/analytics/equity', self.get_equity_curve)

        return app

    async def start(self) -> web.AppRunner:
        """Start the API server and return the runner for cleanup."""
        app = self.create_app()
        runner = web.AppRunner(app)
        await runner.setup()

        site = web.TCPSite(runner, '0.0.0.0', self.port)
        await site.start()

        self.logger.ok(f"Journal API server running on port {self.port}", emoji="🚀")
        return runner


async def run(config: Dict[str, Any], logger) -> None:
    """Entry point for orchestrator."""
    orchestrator = JournalOrchestrator(config, logger)
    runner = await orchestrator.start()

    try:
        # Run forever until cancelled
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        logger.info("Orchestrator cancelled", emoji="🛑")
    finally:
        logger.info("Shutting down API server", emoji="🛑")
        await runner.cleanup()
