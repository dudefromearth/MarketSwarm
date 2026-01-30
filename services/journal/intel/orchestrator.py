# services/journal/intel/orchestrator.py
"""API server and main loop for the FOTW Trade Log service (v2)."""

import asyncio
import json
from typing import Dict, Any, Optional
from datetime import datetime

from aiohttp import web

from .db_v2 import JournalDBv2
from .models_v2 import TradeLog, Trade, TradeEvent, Symbol, Setting
from .analytics_v2 import AnalyticsV2


class JournalOrchestrator:
    """REST API server for the FOTW Trade Log service."""

    def __init__(self, config: Dict[str, Any], logger):
        self.config = config
        self.logger = logger
        self.port = int(config.get('JOURNAL_PORT', 3002))
        self.db = JournalDBv2()
        self.analytics = AnalyticsV2(self.db)

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

    # ==================== Trade Log Endpoints ====================

    async def list_logs(self, request: web.Request) -> web.Response:
        """GET /api/logs - List all trade logs."""
        try:
            include_inactive = request.query.get('include_inactive', 'false') == 'true'
            logs = self.db.list_logs(include_inactive=include_inactive)

            # Get summaries for each log
            log_data = []
            for log in logs:
                summary = self.db.get_log_summary(log.id)
                log_data.append(summary)

            return self._json_response({
                'success': True,
                'data': log_data,
                'count': len(log_data)
            })
        except Exception as e:
            self.logger.error(f"list_logs error: {e}")
            return self._error_response(str(e), 500)

    async def get_log(self, request: web.Request) -> web.Response:
        """GET /api/logs/:id - Get a single trade log with summary."""
        try:
            log_id = request.match_info['id']
            summary = self.db.get_log_summary(log_id)

            if not summary:
                return self._error_response('Trade log not found', 404)

            return self._json_response({
                'success': True,
                'data': summary
            })
        except Exception as e:
            self.logger.error(f"get_log error: {e}")
            return self._error_response(str(e), 500)

    async def create_log(self, request: web.Request) -> web.Response:
        """POST /api/logs - Create a new trade log."""
        try:
            body = await request.json()

            if 'name' not in body:
                return self._error_response('name is required')
            if 'starting_capital' not in body:
                return self._error_response('starting_capital is required')

            # Convert dollars to cents if needed
            starting_capital = body['starting_capital']
            if isinstance(starting_capital, float) or starting_capital < 10000:
                # Assume dollars, convert to cents
                starting_capital = int(starting_capital * 100)

            risk_per_trade = body.get('risk_per_trade')
            if risk_per_trade and (isinstance(risk_per_trade, float) or risk_per_trade < 1000):
                risk_per_trade = int(risk_per_trade * 100)

            log = TradeLog(
                id=TradeLog.new_id(),
                name=body['name'],
                starting_capital=starting_capital,
                risk_per_trade=risk_per_trade,
                max_position_size=body.get('max_position_size'),
                intent=body.get('intent'),
                constraints=json.dumps(body.get('constraints')) if body.get('constraints') else None,
                regime_assumptions=body.get('regime_assumptions'),
                notes=body.get('notes')
            )

            created = self.db.create_log(log)
            self.logger.info(f"Created trade log '{created.name}' with ${starting_capital/100:.2f} capital", emoji="📒")

            return self._json_response({
                'success': True,
                'data': created.to_api_dict()
            }, 201)

        except Exception as e:
            self.logger.error(f"create_log error: {e}")
            return self._error_response(str(e), 500)

    async def update_log(self, request: web.Request) -> web.Response:
        """PUT /api/logs/:id - Update trade log metadata (not starting params)."""
        try:
            log_id = request.match_info['id']
            body = await request.json()

            log = self.db.update_log(log_id, body)

            if not log:
                return self._error_response('Trade log not found', 404)

            return self._json_response({
                'success': True,
                'data': log.to_api_dict()
            })
        except Exception as e:
            self.logger.error(f"update_log error: {e}")
            return self._error_response(str(e), 500)

    async def delete_log(self, request: web.Request) -> web.Response:
        """DELETE /api/logs/:id - Soft delete a trade log."""
        try:
            log_id = request.match_info['id']
            deleted = self.db.delete_log(log_id)

            if not deleted:
                return self._error_response('Trade log not found', 404)

            self.logger.info(f"Archived trade log {log_id}", emoji="📦")

            return self._json_response({
                'success': True,
                'message': 'Trade log archived'
            })
        except Exception as e:
            self.logger.error(f"delete_log error: {e}")
            return self._error_response(str(e), 500)

    # ==================== Trade Endpoints (Log-Scoped) ====================

    async def list_trades(self, request: web.Request) -> web.Response:
        """GET /api/logs/:logId/trades - List trades in a log."""
        try:
            log_id = request.match_info['logId']
            params = request.query

            trades = self.db.list_trades(
                log_id=log_id,
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
                'data': [t.to_api_dict() for t in trades],
                'count': len(trades)
            })
        except Exception as e:
            self.logger.error(f"list_trades error: {e}")
            return self._error_response(str(e), 500)

    async def get_trade(self, request: web.Request) -> web.Response:
        """GET /api/trades/:id - Get a single trade with events."""
        try:
            trade_id = request.match_info['id']
            trade_data = self.db.get_trade_with_events(trade_id)

            if not trade_data:
                return self._error_response('Trade not found', 404)

            return self._json_response({
                'success': True,
                'data': trade_data
            })
        except Exception as e:
            self.logger.error(f"get_trade error: {e}")
            return self._error_response(str(e), 500)

    async def create_trade(self, request: web.Request) -> web.Response:
        """POST /api/logs/:logId/trades - Create a new trade."""
        try:
            log_id = request.match_info['logId']
            body = await request.json()

            # Verify log exists
            log = self.db.get_log(log_id)
            if not log:
                return self._error_response('Trade log not found', 404)

            # Set defaults
            entry_time = body.get('entry_time') or datetime.utcnow().isoformat()

            # Convert prices to cents if needed
            entry_price = body['entry_price']
            if isinstance(entry_price, float) or entry_price < 1000:
                entry_price = int(entry_price * 100)

            planned_risk = body.get('planned_risk')
            if planned_risk and (isinstance(planned_risk, float) or planned_risk < 1000):
                planned_risk = int(planned_risk * 100)

            max_profit = body.get('max_profit')
            if max_profit and (isinstance(max_profit, float) or max_profit < 1000):
                max_profit = int(max_profit * 100)

            max_loss = body.get('max_loss')
            if max_loss and (isinstance(max_loss, float) or max_loss < 1000):
                max_loss = int(max_loss * 100)

            trade = Trade(
                id=Trade.new_id(),
                log_id=log_id,
                symbol=body.get('symbol', 'SPX'),
                underlying=body.get('underlying', 'I:SPX'),
                strategy=body['strategy'],
                side=body['side'],
                strike=float(body['strike']),
                width=body.get('width'),
                dte=body.get('dte'),
                quantity=int(body.get('quantity', 1)),
                entry_time=entry_time,
                entry_price=entry_price,
                entry_spot=body.get('entry_spot'),
                entry_iv=body.get('entry_iv'),
                planned_risk=planned_risk or max_loss,  # Default to max_loss
                max_profit=max_profit,
                max_loss=max_loss,
                notes=body.get('notes'),
                tags=body.get('tags', []),
                source=body.get('source', 'manual'),
                playbook_id=body.get('playbook_id')
            )

            created = self.db.create_trade(trade)
            self.logger.info(f"Created trade: {created.strategy} {created.strike} @ ${entry_price/100:.2f}", emoji="📝")

            return self._json_response({
                'success': True,
                'data': created.to_api_dict()
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
            protected = ['id', 'log_id', 'created_at']
            updates = {k: v for k, v in body.items() if k not in protected}

            # Handle tags serialization
            if 'tags' in updates:
                updates['tags'] = json.dumps(updates['tags'])

            trade = self.db.update_trade(trade_id, updates)

            if not trade:
                return self._error_response('Trade not found', 404)

            return self._json_response({
                'success': True,
                'data': trade.to_api_dict()
            })
        except Exception as e:
            self.logger.error(f"update_trade error: {e}")
            return self._error_response(str(e), 500)

    async def add_adjustment(self, request: web.Request) -> web.Response:
        """POST /api/trades/:id/adjust - Add an adjustment event."""
        try:
            trade_id = request.match_info['id']
            body = await request.json()

            if 'price' not in body:
                return self._error_response('price is required')
            if 'quantity_change' not in body:
                return self._error_response('quantity_change is required')

            # Convert price to cents
            price = body['price']
            if isinstance(price, float) or price < 1000:
                price = int(price * 100)

            event = self.db.add_adjustment(
                trade_id=trade_id,
                price=price,
                quantity_change=int(body['quantity_change']),
                spot=body.get('spot'),
                notes=body.get('notes'),
                event_time=body.get('event_time')
            )

            if not event:
                return self._error_response('Trade not found or already closed', 404)

            self.logger.info(f"Adjusted trade {trade_id}: {body['quantity_change']:+d} @ ${price/100:.2f}", emoji="📝")

            return self._json_response({
                'success': True,
                'data': event.to_api_dict()
            })
        except Exception as e:
            self.logger.error(f"add_adjustment error: {e}")
            return self._error_response(str(e), 500)

    async def close_trade(self, request: web.Request) -> web.Response:
        """POST /api/trades/:id/close - Close a trade."""
        try:
            trade_id = request.match_info['id']
            body = await request.json()

            if 'exit_price' not in body:
                return self._error_response('exit_price is required')

            # Convert price to cents
            exit_price = body['exit_price']
            if isinstance(exit_price, float) or exit_price < 1000:
                exit_price = int(exit_price * 100)

            trade = self.db.close_trade(
                trade_id=trade_id,
                exit_price=exit_price,
                exit_spot=body.get('exit_spot'),
                exit_time=body.get('exit_time'),
                notes=body.get('notes')
            )

            if not trade:
                return self._error_response('Trade not found or already closed', 404)

            pnl_dollars = (trade.pnl or 0) / 100
            pnl_str = f"+${pnl_dollars:.2f}" if pnl_dollars >= 0 else f"-${abs(pnl_dollars):.2f}"
            self.logger.info(f"Closed trade {trade_id}: {pnl_str}", emoji="✅")

            return self._json_response({
                'success': True,
                'data': trade.to_api_dict()
            })
        except Exception as e:
            self.logger.error(f"close_trade error: {e}")
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

    # ==================== Analytics Endpoints (Log-Scoped) ====================

    async def get_log_analytics(self, request: web.Request) -> web.Response:
        """GET /api/logs/:logId/analytics - Get full analytics for a log."""
        try:
            log_id = request.match_info['logId']
            analytics = self.analytics.get_full_analytics(log_id)

            if not analytics:
                return self._error_response('Trade log not found', 404)

            return self._json_response({
                'success': True,
                'data': analytics.to_api_dict()
            })
        except Exception as e:
            self.logger.error(f"get_log_analytics error: {e}")
            return self._error_response(str(e), 500)

    async def get_log_equity(self, request: web.Request) -> web.Response:
        """GET /api/logs/:logId/equity - Get equity curve for a log."""
        try:
            log_id = request.match_info['logId']
            params = request.query

            equity_points = self.analytics.get_equity_curve(
                log_id,
                from_date=params.get('from'),
                to_date=params.get('to')
            )

            return self._json_response({
                'success': True,
                'data': {
                    'equity': [p.to_dict() for p in equity_points]
                }
            })
        except Exception as e:
            self.logger.error(f"get_log_equity error: {e}")
            return self._error_response(str(e), 500)

    async def get_log_drawdown(self, request: web.Request) -> web.Response:
        """GET /api/logs/:logId/drawdown - Get drawdown curve for a log."""
        try:
            log_id = request.match_info['logId']
            params = request.query

            drawdown_points = self.analytics.get_drawdown_curve(
                log_id,
                from_date=params.get('from'),
                to_date=params.get('to')
            )

            return self._json_response({
                'success': True,
                'data': {
                    'drawdown': [p.to_dict() for p in drawdown_points]
                }
            })
        except Exception as e:
            self.logger.error(f"get_log_drawdown error: {e}")
            return self._error_response(str(e), 500)

    async def get_return_distribution(self, request: web.Request) -> web.Response:
        """GET /api/logs/:logId/distribution - Get return distribution histogram for a log."""
        try:
            log_id = request.match_info['logId']
            params = request.query

            # Bin size in dollars (default $50)
            bin_size_dollars = int(params.get('bin_size', 50))
            bin_size_cents = bin_size_dollars * 100

            distribution = self.analytics.get_return_distribution(log_id, bin_size_cents)

            return self._json_response({
                'success': True,
                'data': {
                    'distribution': distribution,
                    'bin_size_dollars': bin_size_dollars
                }
            })
        except Exception as e:
            self.logger.error(f"get_return_distribution error: {e}")
            return self._error_response(str(e), 500)

    # ==================== Symbols ====================

    async def list_symbols(self, request: web.Request) -> web.Response:
        """GET /api/symbols - List all symbols."""
        try:
            params = request.query
            include_disabled = params.get('include_disabled', '').lower() == 'true'
            asset_type = params.get('asset_type')

            symbols = self.db.list_symbols(include_disabled=include_disabled)

            if asset_type:
                symbols = [s for s in symbols if s.asset_type == asset_type]

            return self._json_response({
                'success': True,
                'data': [s.to_dict() for s in symbols],
                'count': len(symbols)
            })
        except Exception as e:
            self.logger.error(f"list_symbols error: {e}")
            return self._error_response(str(e), 500)

    async def get_symbol(self, request: web.Request) -> web.Response:
        """GET /api/symbols/:symbol - Get a single symbol."""
        try:
            symbol = request.match_info['symbol']
            sym = self.db.get_symbol(symbol)

            if not sym:
                return self._error_response(f"Symbol {symbol} not found", 404)

            return self._json_response({
                'success': True,
                'data': sym.to_dict()
            })
        except Exception as e:
            self.logger.error(f"get_symbol error: {e}")
            return self._error_response(str(e), 500)

    async def add_symbol(self, request: web.Request) -> web.Response:
        """POST /api/symbols - Add a new symbol."""
        try:
            body = await request.json()

            required = ['symbol', 'name', 'asset_type', 'multiplier']
            for field in required:
                if field not in body:
                    return self._error_response(f"Missing required field: {field}", 400)

            # Check if symbol already exists
            existing = self.db.get_symbol(body['symbol'])
            if existing:
                return self._error_response(f"Symbol {body['symbol']} already exists", 409)

            symbol = Symbol(
                symbol=body['symbol'].upper(),
                name=body['name'],
                asset_type=body['asset_type'],
                multiplier=int(body['multiplier']),
                enabled=body.get('enabled', True)
            )

            created = self.db.add_symbol(symbol)

            return self._json_response({
                'success': True,
                'data': created.to_dict()
            }, 201)
        except Exception as e:
            self.logger.error(f"add_symbol error: {e}")
            return self._error_response(str(e), 500)

    async def update_symbol(self, request: web.Request) -> web.Response:
        """PUT /api/symbols/:symbol - Update a symbol."""
        try:
            symbol = request.match_info['symbol']
            body = await request.json()

            updated = self.db.update_symbol(symbol, body)
            if not updated:
                return self._error_response(f"Symbol {symbol} not found", 404)

            return self._json_response({
                'success': True,
                'data': updated.to_dict()
            })
        except Exception as e:
            self.logger.error(f"update_symbol error: {e}")
            return self._error_response(str(e), 500)

    async def delete_symbol(self, request: web.Request) -> web.Response:
        """DELETE /api/symbols/:symbol - Delete a user-added symbol."""
        try:
            symbol = request.match_info['symbol']

            # Check if it's a default symbol
            sym = self.db.get_symbol(symbol)
            if sym and sym.is_default:
                return self._error_response("Cannot delete default symbols", 403)

            deleted = self.db.delete_symbol(symbol)
            if not deleted:
                return self._error_response(f"Symbol {symbol} not found or is a default", 404)

            return self._json_response({
                'success': True,
                'message': f"Symbol {symbol} deleted"
            })
        except Exception as e:
            self.logger.error(f"delete_symbol error: {e}")
            return self._error_response(str(e), 500)

    # ==================== Settings ====================

    async def get_settings(self, request: web.Request) -> web.Response:
        """GET /api/settings - Get all settings."""
        try:
            params = request.query
            scope = params.get('scope', 'global')
            category = params.get('category')

            if category:
                settings = self.db.get_settings_by_category(category, scope)
                data = {s.key: s.get_value() for s in settings}
            else:
                data = self.db.get_all_settings(scope)

            return self._json_response({
                'success': True,
                'data': data,
                'scope': scope
            })
        except Exception as e:
            self.logger.error(f"get_settings error: {e}")
            return self._error_response(str(e), 500)

    async def get_setting(self, request: web.Request) -> web.Response:
        """GET /api/settings/:key - Get a single setting."""
        try:
            key = request.match_info['key']
            params = request.query
            scope = params.get('scope', 'global')
            log_id = params.get('log_id')

            # If log_id provided, get effective setting (with per-log override)
            if log_id:
                value = self.db.get_effective_setting(key, log_id)
                return self._json_response({
                    'success': True,
                    'data': {'key': key, 'value': value, 'effective': True}
                })

            setting = self.db.get_setting(key, scope)
            if not setting:
                return self._error_response(f"Setting {key} not found", 404)

            return self._json_response({
                'success': True,
                'data': {
                    'key': setting.key,
                    'value': setting.get_value(),
                    'category': setting.category,
                    'scope': setting.scope,
                    'description': setting.description
                }
            })
        except Exception as e:
            self.logger.error(f"get_setting error: {e}")
            return self._error_response(str(e), 500)

    async def set_setting(self, request: web.Request) -> web.Response:
        """PUT /api/settings/:key - Set a setting value."""
        try:
            key = request.match_info['key']
            body = await request.json()

            if 'value' not in body:
                return self._error_response("Missing required field: value", 400)
            if 'category' not in body:
                return self._error_response("Missing required field: category", 400)

            scope = body.get('scope', 'global')
            description = body.get('description')

            setting = self.db.set_setting(
                key=key,
                value=body['value'],
                category=body['category'],
                scope=scope,
                description=description
            )

            return self._json_response({
                'success': True,
                'data': {
                    'key': setting.key,
                    'value': setting.get_value(),
                    'category': setting.category,
                    'scope': setting.scope
                }
            })
        except Exception as e:
            self.logger.error(f"set_setting error: {e}")
            return self._error_response(str(e), 500)

    async def delete_setting(self, request: web.Request) -> web.Response:
        """DELETE /api/settings/:key - Delete a setting."""
        try:
            key = request.match_info['key']
            params = request.query
            scope = params.get('scope', 'global')

            deleted = self.db.delete_setting(key, scope)
            if not deleted:
                return self._error_response(f"Setting {key} not found", 404)

            return self._json_response({
                'success': True,
                'message': f"Setting {key} deleted"
            })
        except Exception as e:
            self.logger.error(f"delete_setting error: {e}")
            return self._error_response(str(e), 500)

    # ==================== Legacy Endpoints (for backwards compatibility) ====================

    async def legacy_list_trades(self, request: web.Request) -> web.Response:
        """GET /api/trades - Legacy: List trades from first active log."""
        try:
            logs = self.db.list_logs()
            if not logs:
                return self._json_response({
                    'success': True,
                    'data': [],
                    'count': 0
                })

            # Use first log for legacy endpoint
            log_id = logs[0].id
            params = request.query

            trades = self.db.list_trades(
                log_id=log_id,
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
                'data': [t.to_api_dict() for t in trades],
                'count': len(trades)
            })
        except Exception as e:
            self.logger.error(f"legacy_list_trades error: {e}")
            return self._error_response(str(e), 500)

    async def legacy_create_trade(self, request: web.Request) -> web.Response:
        """POST /api/trades - Legacy: Create trade in first active log."""
        try:
            logs = self.db.list_logs()
            if not logs:
                # Create default log
                default_log = TradeLog(
                    id=TradeLog.new_id(),
                    name='Default Log',
                    starting_capital=2500000,  # $25,000
                    intent='Auto-created default log'
                )
                self.db.create_log(default_log)
                logs = [default_log]

            # Inject log_id and forward to normal create
            request._match_info = {'logId': logs[0].id}
            return await self.create_trade(request)
        except Exception as e:
            self.logger.error(f"legacy_create_trade error: {e}")
            return self._error_response(str(e), 500)

    async def legacy_analytics(self, request: web.Request) -> web.Response:
        """GET /api/analytics - Legacy: Analytics from first active log."""
        try:
            logs = self.db.list_logs()
            if not logs:
                return self._json_response({
                    'success': True,
                    'data': {'summary': {}}
                })

            analytics = self.analytics.get_full_analytics(logs[0].id)

            return self._json_response({
                'success': True,
                'data': {
                    'summary': analytics.to_api_dict() if analytics else {}
                }
            })
        except Exception as e:
            self.logger.error(f"legacy_analytics error: {e}")
            return self._error_response(str(e), 500)

    async def legacy_equity(self, request: web.Request) -> web.Response:
        """GET /api/analytics/equity - Legacy: Equity from first active log."""
        try:
            logs = self.db.list_logs()
            if not logs:
                return self._json_response({
                    'success': True,
                    'data': {'equity': []}
                })

            equity_points = self.analytics.get_equity_curve(logs[0].id)

            return self._json_response({
                'success': True,
                'data': {
                    'equity': [p.to_dict() for p in equity_points]
                }
            })
        except Exception as e:
            self.logger.error(f"legacy_equity error: {e}")
            return self._error_response(str(e), 500)

    # ==================== Health & App Setup ====================

    async def health_check(self, request: web.Request) -> web.Response:
        """GET /health - Health check endpoint."""
        return self._json_response({
            'success': True,
            'service': 'journal',
            'version': 'v2',
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

        # Trade Log CRUD (v2)
        app.router.add_get('/api/logs', self.list_logs)
        app.router.add_get('/api/logs/{id}', self.get_log)
        app.router.add_post('/api/logs', self.create_log)
        app.router.add_put('/api/logs/{id}', self.update_log)
        app.router.add_delete('/api/logs/{id}', self.delete_log)

        # Log-scoped trades (v2)
        app.router.add_get('/api/logs/{logId}/trades', self.list_trades)
        app.router.add_post('/api/logs/{logId}/trades', self.create_trade)

        # Trade operations
        app.router.add_get('/api/trades/{id}', self.get_trade)
        app.router.add_put('/api/trades/{id}', self.update_trade)
        app.router.add_delete('/api/trades/{id}', self.delete_trade)
        app.router.add_post('/api/trades/{id}/adjust', self.add_adjustment)
        app.router.add_post('/api/trades/{id}/close', self.close_trade)

        # Log-scoped analytics (v2)
        app.router.add_get('/api/logs/{logId}/analytics', self.get_log_analytics)
        app.router.add_get('/api/logs/{logId}/equity', self.get_log_equity)
        app.router.add_get('/api/logs/{logId}/drawdown', self.get_log_drawdown)
        app.router.add_get('/api/logs/{logId}/distribution', self.get_return_distribution)

        # Symbols registry
        app.router.add_get('/api/symbols', self.list_symbols)
        app.router.add_get('/api/symbols/{symbol}', self.get_symbol)
        app.router.add_post('/api/symbols', self.add_symbol)
        app.router.add_put('/api/symbols/{symbol}', self.update_symbol)
        app.router.add_delete('/api/symbols/{symbol}', self.delete_symbol)

        # Settings
        app.router.add_get('/api/settings', self.get_settings)
        app.router.add_get('/api/settings/{key}', self.get_setting)
        app.router.add_put('/api/settings/{key}', self.set_setting)
        app.router.add_delete('/api/settings/{key}', self.delete_setting)

        # Legacy endpoints (backwards compatibility)
        app.router.add_get('/api/trades', self.legacy_list_trades)
        app.router.add_post('/api/trades', self.legacy_create_trade)
        app.router.add_get('/api/analytics', self.legacy_analytics)
        app.router.add_get('/api/analytics/equity', self.legacy_equity)

        return app

    async def start(self) -> web.AppRunner:
        """Start the API server and return the runner for cleanup."""
        app = self.create_app()
        runner = web.AppRunner(app)
        await runner.setup()

        site = web.TCPSite(runner, '0.0.0.0', self.port)
        await site.start()

        self.logger.ok(f"FOTW Trade Log API (v2) running on port {self.port}", emoji="📒")
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
