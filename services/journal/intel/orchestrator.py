# services/journal/intel/orchestrator.py
"""API server and main loop for the FOTW Trade Log service (v2)."""

import asyncio
import csv
import io
import json
import os
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

from aiohttp import web
import openpyxl
from openpyxl.utils import get_column_letter

from .db_v2 import JournalDBv2
from .models_v2 import (
    TradeLog, Trade, TradeEvent, Symbol, Setting,
    JournalEntry, JournalRetrospective, JournalTradeRef, JournalAttachment
)
from .analytics_v2 import AnalyticsV2
from .auth import JournalAuth, require_auth, optional_auth


class JournalOrchestrator:
    """REST API server for the FOTW Trade Log service."""

    def __init__(self, config: Dict[str, Any], logger):
        self.config = config
        self.logger = logger
        self.port = int(config.get('JOURNAL_PORT', 3002))
        self.db = JournalDBv2(config)
        self.analytics = AnalyticsV2(self.db)
        self.auth = JournalAuth(config, self.db._pool)

        # Journal attachments storage
        default_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'attachments')
        self.attachments_path = Path(config.get('JOURNAL_ATTACHMENTS_PATH', default_path))
        self.attachments_path.mkdir(parents=True, exist_ok=True)
        self.max_attachment_size = 10 * 1024 * 1024  # 10MB

    def _json_response(self, data: Any, status: int = 200) -> web.Response:
        """Create a JSON response with CORS headers."""
        return web.Response(
            text=json.dumps(data, default=str),
            status=status,
            content_type='application/json',
            headers={
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type, Authorization',
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
                'Access-Control-Allow-Headers': 'Content-Type, Authorization',
            }
        )

    # ==================== Trade Log Endpoints ====================

    async def list_logs(self, request: web.Request) -> web.Response:
        """GET /api/logs - List trade logs for authenticated user."""
        try:
            # Get authenticated user (optional - returns all if no auth)
            user = await self.auth.get_request_user(request)
            user_id = user['id'] if user else None

            include_inactive = request.query.get('include_inactive', 'false') == 'true'
            logs = self.db.list_logs(user_id=user_id, include_inactive=include_inactive)

            # Get summaries for each log
            log_data = []
            for log in logs:
                summary = self.db.get_log_summary(log.id, user_id)
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

            # Get authenticated user (optional)
            user = await self.auth.get_request_user(request)
            user_id = user['id'] if user else None

            summary = self.db.get_log_summary(log_id, user_id)

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
            # Require authentication for creating logs
            user = await self.auth.get_request_user(request)
            if not user:
                return self._error_response('Authentication required', 401)

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
                user_id=user['id'],  # Set owner from authenticated user
                starting_capital=starting_capital,
                risk_per_trade=risk_per_trade,
                max_position_size=body.get('max_position_size'),
                intent=body.get('intent'),
                constraints=json.dumps(body.get('constraints')) if body.get('constraints') else None,
                regime_assumptions=body.get('regime_assumptions'),
                notes=body.get('notes')
            )

            created = self.db.create_log(log)
            self.logger.info(f"Created trade log '{created.name}' for user {user['id']} with ${starting_capital/100:.2f} capital", emoji="📒")

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

    # ==================== Export/Import ====================

    # CSV/Excel column definitions
    EXPORT_COLUMNS = [
        'entry_time', 'symbol', 'underlying', 'strategy', 'side', 'strike', 'width',
        'dte', 'quantity', 'entry_price', 'entry_spot', 'exit_time', 'exit_price',
        'exit_spot', 'pnl', 'r_multiple', 'status', 'planned_risk', 'max_profit',
        'max_loss', 'notes', 'tags', 'source'
    ]

    async def export_trades(self, request: web.Request) -> web.Response:
        """GET /api/logs/:logId/export - Export trades as CSV or Excel."""
        try:
            log_id = request.match_info['logId']
            format_type = request.query.get('format', 'csv').lower()

            # Verify log exists
            log = self.db.get_log(log_id)
            if not log:
                return self._error_response('Trade log not found', 404)

            # Get all trades
            trades = self.db.list_trades(log_id=log_id, limit=100000)

            if format_type == 'xlsx':
                return await self._export_excel(trades, log.name)
            else:
                return await self._export_csv(trades, log.name)

        except Exception as e:
            self.logger.error(f"export_trades error: {e}")
            return self._error_response(str(e), 500)

    async def _export_csv(self, trades: List[Trade], log_name: str) -> web.Response:
        """Generate CSV file from trades."""
        output = io.StringIO()
        writer = csv.writer(output)

        # Header row
        writer.writerow(self.EXPORT_COLUMNS)

        # Data rows
        for trade in trades:
            row = self._trade_to_export_row(trade)
            writer.writerow(row)

        csv_content = output.getvalue()
        filename = f"{log_name.replace(' ', '_')}_trades.csv"

        return web.Response(
            body=csv_content,
            content_type='text/csv',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Access-Control-Allow-Origin': '*',
            }
        )

    async def _export_excel(self, trades: List[Trade], log_name: str) -> web.Response:
        """Generate Excel file from trades."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Trades"

        # Header row with styling
        for col, header in enumerate(self.EXPORT_COLUMNS, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = openpyxl.styles.Font(bold=True)

        # Data rows
        for row_num, trade in enumerate(trades, 2):
            row_data = self._trade_to_export_row(trade)
            for col, value in enumerate(row_data, 1):
                ws.cell(row=row_num, column=col, value=value)

        # Auto-size columns
        for col in range(1, len(self.EXPORT_COLUMNS) + 1):
            ws.column_dimensions[get_column_letter(col)].width = 15

        # Save to bytes
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        filename = f"{log_name.replace(' ', '_')}_trades.xlsx"

        return web.Response(
            body=output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Access-Control-Allow-Origin': '*',
            }
        )

    def _trade_to_export_row(self, trade: Trade) -> list:
        """Convert a trade to an export row with dollars instead of cents."""
        return [
            trade.entry_time,
            trade.symbol,
            trade.underlying,
            trade.strategy,
            trade.side,
            trade.strike,
            trade.width,
            trade.dte,
            trade.quantity,
            trade.entry_price / 100 if trade.entry_price else None,  # cents to dollars
            trade.entry_spot,
            trade.exit_time,
            trade.exit_price / 100 if trade.exit_price else None,  # cents to dollars
            trade.exit_spot,
            trade.pnl / 100 if trade.pnl is not None else None,  # cents to dollars
            trade.r_multiple,
            trade.status,
            trade.planned_risk / 100 if trade.planned_risk else None,
            trade.max_profit / 100 if trade.max_profit else None,
            trade.max_loss / 100 if trade.max_loss else None,
            trade.notes,
            ','.join(trade.tags) if trade.tags else '',
            trade.source
        ]

    async def import_trades(self, request: web.Request) -> web.Response:
        """POST /api/logs/:logId/import - Import trades from CSV or Excel."""
        try:
            log_id = request.match_info['logId']

            # Verify log exists
            log = self.db.get_log(log_id)
            if not log:
                return self._error_response('Trade log not found', 404)

            # Read multipart data
            reader = await request.multipart()
            field = await reader.next()

            if not field:
                return self._error_response('No file uploaded', 400)

            filename = field.filename or 'upload'
            content = await field.read()

            # Determine format from filename or content
            if filename.endswith('.xlsx') or filename.endswith('.xls'):
                trades_data = self._parse_excel(content)
            else:
                trades_data = self._parse_csv(content)

            if not trades_data:
                return self._error_response('No valid trades found in file', 400)

            # Create trades
            created_count = 0
            errors = []

            for i, row in enumerate(trades_data):
                try:
                    trade = self._row_to_trade(row, log_id)
                    if trade:
                        self.db.create_trade(trade)
                        created_count += 1
                except Exception as e:
                    errors.append(f"Row {i + 2}: {str(e)}")

            self.logger.info(f"Imported {created_count} trades into '{log.name}'", emoji="📥")

            return self._json_response({
                'success': True,
                'imported': created_count,
                'errors': errors[:10] if errors else [],  # Limit error messages
                'total_errors': len(errors)
            })

        except Exception as e:
            self.logger.error(f"import_trades error: {e}")
            return self._error_response(str(e), 500)

    def _parse_csv(self, content: bytes) -> List[dict]:
        """Parse CSV content into list of dicts."""
        try:
            text = content.decode('utf-8')
        except UnicodeDecodeError:
            text = content.decode('latin-1')

        reader = csv.DictReader(io.StringIO(text))
        return list(reader)

    def _parse_excel(self, content: bytes) -> List[dict]:
        """Parse Excel content into list of dicts."""
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True)
        ws = wb.active

        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return []

        # First row is headers
        headers = [str(h).lower().strip() if h else '' for h in rows[0]]
        result = []

        for row in rows[1:]:
            if not any(row):  # Skip empty rows
                continue
            row_dict = {}
            for i, value in enumerate(row):
                if i < len(headers) and headers[i]:
                    row_dict[headers[i]] = value
            result.append(row_dict)

        return result

    def _row_to_trade(self, row: dict, log_id: str) -> Optional[Trade]:
        """Convert an import row to a Trade object."""
        # Normalize keys to lowercase
        row = {k.lower().strip(): v for k, v in row.items() if k}

        # Required fields
        if not row.get('strategy') or not row.get('side') or not row.get('strike'):
            return None

        # Parse entry_time
        entry_time = row.get('entry_time')
        if isinstance(entry_time, datetime):
            entry_time = entry_time.isoformat()
        elif not entry_time:
            entry_time = datetime.utcnow().isoformat()

        # Parse exit_time
        exit_time = row.get('exit_time')
        if isinstance(exit_time, datetime):
            exit_time = exit_time.isoformat()
        elif exit_time == '' or exit_time is None:
            exit_time = None

        # Convert prices from dollars to cents
        def to_cents(val):
            if val is None or val == '':
                return None
            try:
                return int(float(val) * 100)
            except (ValueError, TypeError):
                return None

        entry_price = to_cents(row.get('entry_price'))
        exit_price = to_cents(row.get('exit_price'))
        pnl = to_cents(row.get('pnl'))
        planned_risk = to_cents(row.get('planned_risk'))
        max_profit = to_cents(row.get('max_profit'))
        max_loss = to_cents(row.get('max_loss'))

        # Parse numeric fields
        def to_float(val):
            if val is None or val == '':
                return None
            try:
                return float(val)
            except (ValueError, TypeError):
                return None

        def to_int(val):
            if val is None or val == '':
                return None
            try:
                return int(float(val))
            except (ValueError, TypeError):
                return None

        # Parse tags
        tags_raw = row.get('tags', '')
        if isinstance(tags_raw, str):
            tags = [t.strip() for t in tags_raw.split(',') if t.strip()]
        else:
            tags = []

        # Determine status
        status = str(row.get('status', '')).lower()
        if status not in ('open', 'closed'):
            status = 'closed' if exit_price is not None else 'open'

        return Trade(
            id=Trade.new_id(),
            log_id=log_id,
            symbol=str(row.get('symbol', 'SPX')).upper(),
            underlying=str(row.get('underlying', 'I:SPX')),
            strategy=str(row.get('strategy', '')).lower(),
            side=str(row.get('side', '')).lower(),
            strike=to_float(row.get('strike')) or 0,
            width=to_int(row.get('width')),
            dte=to_int(row.get('dte')),
            quantity=to_int(row.get('quantity')) or 1,
            entry_time=entry_time,
            entry_price=entry_price or 0,
            entry_spot=to_float(row.get('entry_spot')),
            exit_time=exit_time,
            exit_price=exit_price,
            exit_spot=to_float(row.get('exit_spot')),
            pnl=pnl,
            r_multiple=to_float(row.get('r_multiple')),
            planned_risk=planned_risk,
            max_profit=max_profit,
            max_loss=max_loss,
            status=status,
            notes=str(row.get('notes', '')) if row.get('notes') else None,
            tags=tags,
            source=str(row.get('source', 'import'))
        )

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

    # ==================== Journal Entry Endpoints ====================

    async def list_journal_entries(self, request: web.Request) -> web.Response:
        """GET /api/journal/entries - List journal entries for authenticated user."""
        try:
            user = await self.auth.get_request_user(request)
            if not user:
                return self._error_response('Authentication required', 401)

            params = request.query
            entries = self.db.list_entries(
                user_id=user['id'],
                from_date=params.get('from'),
                to_date=params.get('to'),
                playbook_only=params.get('playbook_only', '').lower() == 'true',
                limit=int(params.get('limit', 100)),
                offset=int(params.get('offset', 0))
            )

            return self._json_response({
                'success': True,
                'data': [e.to_api_dict() for e in entries],
                'count': len(entries)
            })
        except Exception as e:
            self.logger.error(f"list_journal_entries error: {e}")
            return self._error_response(str(e), 500)

    async def get_journal_entry(self, request: web.Request) -> web.Response:
        """GET /api/journal/entries/:id - Get a single journal entry with attachments and trade refs."""
        try:
            user = await self.auth.get_request_user(request)
            if not user:
                return self._error_response('Authentication required', 401)

            entry_id = request.match_info['id']
            entry = self.db.get_entry(entry_id)

            if not entry:
                return self._error_response('Entry not found', 404)

            if entry.user_id != user['id']:
                return self._error_response('Access denied', 403)

            # Get related data
            trade_refs = self.db.list_trade_refs('entry', entry_id)
            attachments = self.db.list_attachments('entry', entry_id)

            data = entry.to_api_dict()
            data['trade_refs'] = [r.to_api_dict() for r in trade_refs]
            data['attachments'] = [a.to_api_dict() for a in attachments]

            return self._json_response({
                'success': True,
                'data': data
            })
        except Exception as e:
            self.logger.error(f"get_journal_entry error: {e}")
            return self._error_response(str(e), 500)

    async def get_journal_entry_by_date(self, request: web.Request) -> web.Response:
        """GET /api/journal/entries/date/:date - Get entry by date (YYYY-MM-DD)."""
        try:
            user = await self.auth.get_request_user(request)
            if not user:
                return self._error_response('Authentication required', 401)

            date = request.match_info['date']
            entry = self.db.get_entry_by_date(user['id'], date)

            if not entry:
                return self._error_response('Entry not found', 404)

            # Get related data
            trade_refs = self.db.list_trade_refs('entry', entry.id)
            attachments = self.db.list_attachments('entry', entry.id)

            data = entry.to_api_dict()
            data['trade_refs'] = [r.to_api_dict() for r in trade_refs]
            data['attachments'] = [a.to_api_dict() for a in attachments]

            return self._json_response({
                'success': True,
                'data': data
            })
        except Exception as e:
            self.logger.error(f"get_journal_entry_by_date error: {e}")
            return self._error_response(str(e), 500)

    async def create_journal_entry(self, request: web.Request) -> web.Response:
        """POST /api/journal/entries - Create or update entry (upsert by date)."""
        try:
            user = await self.auth.get_request_user(request)
            if not user:
                return self._error_response('Authentication required', 401)

            body = await request.json()

            if 'entry_date' not in body:
                return self._error_response('entry_date is required')

            entry = JournalEntry(
                id=JournalEntry.new_id(),
                user_id=user['id'],
                entry_date=body['entry_date'],
                content=body.get('content'),
                is_playbook_material=body.get('is_playbook_material', False)
            )

            result = self.db.upsert_entry(entry)
            self.logger.info(f"Upserted journal entry for {body['entry_date']}", emoji="📓")

            return self._json_response({
                'success': True,
                'data': result.to_api_dict()
            }, 201)
        except Exception as e:
            self.logger.error(f"create_journal_entry error: {e}")
            return self._error_response(str(e), 500)

    async def update_journal_entry(self, request: web.Request) -> web.Response:
        """PUT /api/journal/entries/:id - Update an entry."""
        try:
            user = await self.auth.get_request_user(request)
            if not user:
                return self._error_response('Authentication required', 401)

            entry_id = request.match_info['id']
            entry = self.db.get_entry(entry_id)

            if not entry:
                return self._error_response('Entry not found', 404)

            if entry.user_id != user['id']:
                return self._error_response('Access denied', 403)

            body = await request.json()
            updated = self.db.update_entry(entry_id, body)

            return self._json_response({
                'success': True,
                'data': updated.to_api_dict()
            })
        except Exception as e:
            self.logger.error(f"update_journal_entry error: {e}")
            return self._error_response(str(e), 500)

    async def delete_journal_entry(self, request: web.Request) -> web.Response:
        """DELETE /api/journal/entries/:id - Delete an entry."""
        try:
            user = await self.auth.get_request_user(request)
            if not user:
                return self._error_response('Authentication required', 401)

            entry_id = request.match_info['id']
            entry = self.db.get_entry(entry_id)

            if not entry:
                return self._error_response('Entry not found', 404)

            if entry.user_id != user['id']:
                return self._error_response('Access denied', 403)

            # Delete attachment files
            attachments = self.db.list_attachments('entry', entry_id)
            for att in attachments:
                try:
                    file_path = Path(att.file_path)
                    if file_path.exists():
                        file_path.unlink()
                except Exception:
                    pass  # Best effort deletion

            deleted = self.db.delete_entry(entry_id)
            self.logger.info(f"Deleted journal entry {entry_id}", emoji="🗑️")

            return self._json_response({
                'success': True,
                'message': 'Entry deleted'
            })
        except Exception as e:
            self.logger.error(f"delete_journal_entry error: {e}")
            return self._error_response(str(e), 500)

    # ==================== Journal Retrospective Endpoints ====================

    async def list_retrospectives(self, request: web.Request) -> web.Response:
        """GET /api/journal/retrospectives - List retrospectives."""
        try:
            user = await self.auth.get_request_user(request)
            if not user:
                return self._error_response('Authentication required', 401)

            params = request.query
            retros = self.db.list_retrospectives(
                user_id=user['id'],
                retro_type=params.get('type'),
                from_date=params.get('from'),
                to_date=params.get('to'),
                playbook_only=params.get('playbook_only', '').lower() == 'true'
            )

            return self._json_response({
                'success': True,
                'data': [r.to_api_dict() for r in retros],
                'count': len(retros)
            })
        except Exception as e:
            self.logger.error(f"list_retrospectives error: {e}")
            return self._error_response(str(e), 500)

    async def get_retrospective(self, request: web.Request) -> web.Response:
        """GET /api/journal/retrospectives/:id - Get a single retrospective."""
        try:
            user = await self.auth.get_request_user(request)
            if not user:
                return self._error_response('Authentication required', 401)

            retro_id = request.match_info['id']
            retro = self.db.get_retrospective(retro_id)

            if not retro:
                return self._error_response('Retrospective not found', 404)

            if retro.user_id != user['id']:
                return self._error_response('Access denied', 403)

            # Get related data
            trade_refs = self.db.list_trade_refs('retrospective', retro_id)
            attachments = self.db.list_attachments('retrospective', retro_id)

            data = retro.to_api_dict()
            data['trade_refs'] = [r.to_api_dict() for r in trade_refs]
            data['attachments'] = [a.to_api_dict() for a in attachments]

            return self._json_response({
                'success': True,
                'data': data
            })
        except Exception as e:
            self.logger.error(f"get_retrospective error: {e}")
            return self._error_response(str(e), 500)

    async def get_retrospective_by_period(self, request: web.Request) -> web.Response:
        """GET /api/journal/retrospectives/:type/:periodStart - Get by type and period."""
        try:
            user = await self.auth.get_request_user(request)
            if not user:
                return self._error_response('Authentication required', 401)

            retro_type = request.match_info['type']
            period_start = request.match_info['periodStart']

            if retro_type not in ('weekly', 'monthly'):
                return self._error_response('Invalid retrospective type', 400)

            retro = self.db.get_retrospective_by_period(user['id'], retro_type, period_start)

            if not retro:
                return self._error_response('Retrospective not found', 404)

            # Get related data
            trade_refs = self.db.list_trade_refs('retrospective', retro.id)
            attachments = self.db.list_attachments('retrospective', retro.id)

            data = retro.to_api_dict()
            data['trade_refs'] = [r.to_api_dict() for r in trade_refs]
            data['attachments'] = [a.to_api_dict() for a in attachments]

            return self._json_response({
                'success': True,
                'data': data
            })
        except Exception as e:
            self.logger.error(f"get_retrospective_by_period error: {e}")
            return self._error_response(str(e), 500)

    async def create_retrospective(self, request: web.Request) -> web.Response:
        """POST /api/journal/retrospectives - Create a retrospective."""
        try:
            user = await self.auth.get_request_user(request)
            if not user:
                return self._error_response('Authentication required', 401)

            body = await request.json()

            required = ['retro_type', 'period_start', 'period_end']
            for field in required:
                if field not in body:
                    return self._error_response(f'{field} is required')

            if body['retro_type'] not in ('weekly', 'monthly'):
                return self._error_response('retro_type must be weekly or monthly')

            # Check if one already exists for this period
            existing = self.db.get_retrospective_by_period(
                user['id'], body['retro_type'], body['period_start']
            )
            if existing:
                return self._error_response('Retrospective already exists for this period', 409)

            retro = JournalRetrospective(
                id=JournalRetrospective.new_id(),
                user_id=user['id'],
                retro_type=body['retro_type'],
                period_start=body['period_start'],
                period_end=body['period_end'],
                content=body.get('content'),
                is_playbook_material=body.get('is_playbook_material', False)
            )

            created = self.db.create_retrospective(retro)
            self.logger.info(f"Created {body['retro_type']} retrospective for {body['period_start']}", emoji="📅")

            return self._json_response({
                'success': True,
                'data': created.to_api_dict()
            }, 201)
        except Exception as e:
            self.logger.error(f"create_retrospective error: {e}")
            return self._error_response(str(e), 500)

    async def update_retrospective(self, request: web.Request) -> web.Response:
        """PUT /api/journal/retrospectives/:id - Update a retrospective."""
        try:
            user = await self.auth.get_request_user(request)
            if not user:
                return self._error_response('Authentication required', 401)

            retro_id = request.match_info['id']
            retro = self.db.get_retrospective(retro_id)

            if not retro:
                return self._error_response('Retrospective not found', 404)

            if retro.user_id != user['id']:
                return self._error_response('Access denied', 403)

            body = await request.json()
            updated = self.db.update_retrospective(retro_id, body)

            return self._json_response({
                'success': True,
                'data': updated.to_api_dict()
            })
        except Exception as e:
            self.logger.error(f"update_retrospective error: {e}")
            return self._error_response(str(e), 500)

    async def delete_retrospective(self, request: web.Request) -> web.Response:
        """DELETE /api/journal/retrospectives/:id - Delete a retrospective."""
        try:
            user = await self.auth.get_request_user(request)
            if not user:
                return self._error_response('Authentication required', 401)

            retro_id = request.match_info['id']
            retro = self.db.get_retrospective(retro_id)

            if not retro:
                return self._error_response('Retrospective not found', 404)

            if retro.user_id != user['id']:
                return self._error_response('Access denied', 403)

            # Delete attachment files
            attachments = self.db.list_attachments('retrospective', retro_id)
            for att in attachments:
                try:
                    file_path = Path(att.file_path)
                    if file_path.exists():
                        file_path.unlink()
                except Exception:
                    pass

            deleted = self.db.delete_retrospective(retro_id)
            self.logger.info(f"Deleted retrospective {retro_id}", emoji="🗑️")

            return self._json_response({
                'success': True,
                'message': 'Retrospective deleted'
            })
        except Exception as e:
            self.logger.error(f"delete_retrospective error: {e}")
            return self._error_response(str(e), 500)

    # ==================== Journal Trade Reference Endpoints ====================

    async def list_entry_trade_refs(self, request: web.Request) -> web.Response:
        """GET /api/journal/entries/:id/trades - List trade refs for an entry."""
        try:
            user = await self.auth.get_request_user(request)
            if not user:
                return self._error_response('Authentication required', 401)

            entry_id = request.match_info['id']
            entry = self.db.get_entry(entry_id)

            if not entry:
                return self._error_response('Entry not found', 404)

            if entry.user_id != user['id']:
                return self._error_response('Access denied', 403)

            refs = self.db.list_trade_refs('entry', entry_id)

            return self._json_response({
                'success': True,
                'data': [r.to_api_dict() for r in refs],
                'count': len(refs)
            })
        except Exception as e:
            self.logger.error(f"list_entry_trade_refs error: {e}")
            return self._error_response(str(e), 500)

    async def add_entry_trade_ref(self, request: web.Request) -> web.Response:
        """POST /api/journal/entries/:id/trades - Add trade reference to entry."""
        try:
            user = await self.auth.get_request_user(request)
            if not user:
                return self._error_response('Authentication required', 401)

            entry_id = request.match_info['id']
            entry = self.db.get_entry(entry_id)

            if not entry:
                return self._error_response('Entry not found', 404)

            if entry.user_id != user['id']:
                return self._error_response('Access denied', 403)

            body = await request.json()
            if 'trade_id' not in body:
                return self._error_response('trade_id is required')

            ref = JournalTradeRef(
                id=JournalTradeRef.new_id(),
                source_type='entry',
                source_id=entry_id,
                trade_id=body['trade_id'],
                note=body.get('note')
            )

            created = self.db.add_trade_ref(ref)

            return self._json_response({
                'success': True,
                'data': created.to_api_dict()
            }, 201)
        except Exception as e:
            self.logger.error(f"add_entry_trade_ref error: {e}")
            return self._error_response(str(e), 500)

    async def list_retro_trade_refs(self, request: web.Request) -> web.Response:
        """GET /api/journal/retrospectives/:id/trades - List trade refs for a retrospective."""
        try:
            user = await self.auth.get_request_user(request)
            if not user:
                return self._error_response('Authentication required', 401)

            retro_id = request.match_info['id']
            retro = self.db.get_retrospective(retro_id)

            if not retro:
                return self._error_response('Retrospective not found', 404)

            if retro.user_id != user['id']:
                return self._error_response('Access denied', 403)

            refs = self.db.list_trade_refs('retrospective', retro_id)

            return self._json_response({
                'success': True,
                'data': [r.to_api_dict() for r in refs],
                'count': len(refs)
            })
        except Exception as e:
            self.logger.error(f"list_retro_trade_refs error: {e}")
            return self._error_response(str(e), 500)

    async def add_retro_trade_ref(self, request: web.Request) -> web.Response:
        """POST /api/journal/retrospectives/:id/trades - Add trade reference to retrospective."""
        try:
            user = await self.auth.get_request_user(request)
            if not user:
                return self._error_response('Authentication required', 401)

            retro_id = request.match_info['id']
            retro = self.db.get_retrospective(retro_id)

            if not retro:
                return self._error_response('Retrospective not found', 404)

            if retro.user_id != user['id']:
                return self._error_response('Access denied', 403)

            body = await request.json()
            if 'trade_id' not in body:
                return self._error_response('trade_id is required')

            ref = JournalTradeRef(
                id=JournalTradeRef.new_id(),
                source_type='retrospective',
                source_id=retro_id,
                trade_id=body['trade_id'],
                note=body.get('note')
            )

            created = self.db.add_trade_ref(ref)

            return self._json_response({
                'success': True,
                'data': created.to_api_dict()
            }, 201)
        except Exception as e:
            self.logger.error(f"add_retro_trade_ref error: {e}")
            return self._error_response(str(e), 500)

    async def delete_trade_ref(self, request: web.Request) -> web.Response:
        """DELETE /api/journal/trade-refs/:id - Remove a trade reference."""
        try:
            user = await self.auth.get_request_user(request)
            if not user:
                return self._error_response('Authentication required', 401)

            ref_id = request.match_info['id']

            # We don't have direct ownership check on refs, but the delete is safe
            deleted = self.db.delete_trade_ref(ref_id)
            if not deleted:
                return self._error_response('Trade reference not found', 404)

            return self._json_response({
                'success': True,
                'message': 'Trade reference deleted'
            })
        except Exception as e:
            self.logger.error(f"delete_trade_ref error: {e}")
            return self._error_response(str(e), 500)

    # ==================== Journal Attachment Endpoints ====================

    def _get_storage_path(self, user_id: int, filename: str) -> Path:
        """Generate storage path for an attachment."""
        now = datetime.utcnow()
        import uuid
        unique_name = f"{uuid.uuid4()}_{filename}"
        path = self.attachments_path / str(user_id) / str(now.year) / f"{now.month:02d}"
        path.mkdir(parents=True, exist_ok=True)
        return path / unique_name

    async def list_entry_attachments(self, request: web.Request) -> web.Response:
        """GET /api/journal/entries/:id/attachments - List attachments for an entry."""
        try:
            user = await self.auth.get_request_user(request)
            if not user:
                return self._error_response('Authentication required', 401)

            entry_id = request.match_info['id']
            entry = self.db.get_entry(entry_id)

            if not entry:
                return self._error_response('Entry not found', 404)

            if entry.user_id != user['id']:
                return self._error_response('Access denied', 403)

            attachments = self.db.list_attachments('entry', entry_id)

            return self._json_response({
                'success': True,
                'data': [a.to_api_dict() for a in attachments],
                'count': len(attachments)
            })
        except Exception as e:
            self.logger.error(f"list_entry_attachments error: {e}")
            return self._error_response(str(e), 500)

    async def upload_entry_attachment(self, request: web.Request) -> web.Response:
        """POST /api/journal/entries/:id/attachments - Upload attachment to entry."""
        try:
            user = await self.auth.get_request_user(request)
            if not user:
                return self._error_response('Authentication required', 401)

            entry_id = request.match_info['id']
            entry = self.db.get_entry(entry_id)

            if not entry:
                return self._error_response('Entry not found', 404)

            if entry.user_id != user['id']:
                return self._error_response('Access denied', 403)

            # Read multipart data
            reader = await request.multipart()
            field = await reader.next()

            if not field:
                return self._error_response('No file uploaded', 400)

            filename = field.filename or 'upload'
            content_type = field.headers.get('Content-Type', 'application/octet-stream')

            # Read file with size limit
            chunks = []
            size = 0
            while True:
                chunk = await field.read_chunk()
                if not chunk:
                    break
                size += len(chunk)
                if size > self.max_attachment_size:
                    return self._error_response(f'File too large (max {self.max_attachment_size // 1024 // 1024}MB)', 400)
                chunks.append(chunk)

            content = b''.join(chunks)

            # Save file
            storage_path = self._get_storage_path(user['id'], filename)
            with open(storage_path, 'wb') as f:
                f.write(content)

            # Create attachment record
            attachment = JournalAttachment(
                id=JournalAttachment.new_id(),
                source_type='entry',
                source_id=entry_id,
                filename=filename,
                file_path=str(storage_path),
                mime_type=content_type,
                file_size=size
            )

            created = self.db.create_attachment(attachment)
            self.logger.info(f"Uploaded attachment '{filename}' to entry {entry_id}", emoji="📎")

            return self._json_response({
                'success': True,
                'data': created.to_api_dict()
            }, 201)
        except Exception as e:
            self.logger.error(f"upload_entry_attachment error: {e}")
            return self._error_response(str(e), 500)

    async def list_retro_attachments(self, request: web.Request) -> web.Response:
        """GET /api/journal/retrospectives/:id/attachments - List attachments for a retrospective."""
        try:
            user = await self.auth.get_request_user(request)
            if not user:
                return self._error_response('Authentication required', 401)

            retro_id = request.match_info['id']
            retro = self.db.get_retrospective(retro_id)

            if not retro:
                return self._error_response('Retrospective not found', 404)

            if retro.user_id != user['id']:
                return self._error_response('Access denied', 403)

            attachments = self.db.list_attachments('retrospective', retro_id)

            return self._json_response({
                'success': True,
                'data': [a.to_api_dict() for a in attachments],
                'count': len(attachments)
            })
        except Exception as e:
            self.logger.error(f"list_retro_attachments error: {e}")
            return self._error_response(str(e), 500)

    async def upload_retro_attachment(self, request: web.Request) -> web.Response:
        """POST /api/journal/retrospectives/:id/attachments - Upload attachment to retrospective."""
        try:
            user = await self.auth.get_request_user(request)
            if not user:
                return self._error_response('Authentication required', 401)

            retro_id = request.match_info['id']
            retro = self.db.get_retrospective(retro_id)

            if not retro:
                return self._error_response('Retrospective not found', 404)

            if retro.user_id != user['id']:
                return self._error_response('Access denied', 403)

            # Read multipart data
            reader = await request.multipart()
            field = await reader.next()

            if not field:
                return self._error_response('No file uploaded', 400)

            filename = field.filename or 'upload'
            content_type = field.headers.get('Content-Type', 'application/octet-stream')

            # Read file with size limit
            chunks = []
            size = 0
            while True:
                chunk = await field.read_chunk()
                if not chunk:
                    break
                size += len(chunk)
                if size > self.max_attachment_size:
                    return self._error_response(f'File too large (max {self.max_attachment_size // 1024 // 1024}MB)', 400)
                chunks.append(chunk)

            content = b''.join(chunks)

            # Save file
            storage_path = self._get_storage_path(user['id'], filename)
            with open(storage_path, 'wb') as f:
                f.write(content)

            # Create attachment record
            attachment = JournalAttachment(
                id=JournalAttachment.new_id(),
                source_type='retrospective',
                source_id=retro_id,
                filename=filename,
                file_path=str(storage_path),
                mime_type=content_type,
                file_size=size
            )

            created = self.db.create_attachment(attachment)
            self.logger.info(f"Uploaded attachment '{filename}' to retrospective {retro_id}", emoji="📎")

            return self._json_response({
                'success': True,
                'data': created.to_api_dict()
            }, 201)
        except Exception as e:
            self.logger.error(f"upload_retro_attachment error: {e}")
            return self._error_response(str(e), 500)

    async def download_attachment(self, request: web.Request) -> web.Response:
        """GET /api/journal/attachments/:id - Download an attachment."""
        try:
            user = await self.auth.get_request_user(request)
            if not user:
                return self._error_response('Authentication required', 401)

            attachment_id = request.match_info['id']
            attachment = self.db.get_attachment(attachment_id)

            if not attachment:
                return self._error_response('Attachment not found', 404)

            # Verify ownership through parent entry/retrospective
            if attachment.source_type == 'entry':
                entry = self.db.get_entry(attachment.source_id)
                if not entry or entry.user_id != user['id']:
                    return self._error_response('Access denied', 403)
            else:
                retro = self.db.get_retrospective(attachment.source_id)
                if not retro or retro.user_id != user['id']:
                    return self._error_response('Access denied', 403)

            file_path = Path(attachment.file_path)
            if not file_path.exists():
                return self._error_response('File not found', 404)

            with open(file_path, 'rb') as f:
                content = f.read()

            return web.Response(
                body=content,
                content_type=attachment.mime_type or 'application/octet-stream',
                headers={
                    'Content-Disposition': f'attachment; filename="{attachment.filename}"',
                    'Access-Control-Allow-Origin': '*',
                }
            )
        except Exception as e:
            self.logger.error(f"download_attachment error: {e}")
            return self._error_response(str(e), 500)

    async def delete_attachment(self, request: web.Request) -> web.Response:
        """DELETE /api/journal/attachments/:id - Delete an attachment."""
        try:
            user = await self.auth.get_request_user(request)
            if not user:
                return self._error_response('Authentication required', 401)

            attachment_id = request.match_info['id']
            attachment = self.db.get_attachment(attachment_id)

            if not attachment:
                return self._error_response('Attachment not found', 404)

            # Verify ownership through parent entry/retrospective
            if attachment.source_type == 'entry':
                entry = self.db.get_entry(attachment.source_id)
                if not entry or entry.user_id != user['id']:
                    return self._error_response('Access denied', 403)
            else:
                retro = self.db.get_retrospective(attachment.source_id)
                if not retro or retro.user_id != user['id']:
                    return self._error_response('Access denied', 403)

            # Delete file
            try:
                file_path = Path(attachment.file_path)
                if file_path.exists():
                    file_path.unlink()
            except Exception:
                pass  # Best effort

            # Delete record
            self.db.delete_attachment(attachment_id)
            self.logger.info(f"Deleted attachment {attachment_id}", emoji="🗑️")

            return self._json_response({
                'success': True,
                'message': 'Attachment deleted'
            })
        except Exception as e:
            self.logger.error(f"delete_attachment error: {e}")
            return self._error_response(str(e), 500)

    # ==================== Calendar View Endpoints (Temporal Gravity) ====================

    async def get_calendar_month(self, request: web.Request) -> web.Response:
        """GET /api/journal/calendar/:year/:month - Get month view with entry indicators."""
        try:
            user = await self.auth.get_request_user(request)
            if not user:
                return self._error_response('Authentication required', 401)

            year = int(request.match_info['year'])
            month = int(request.match_info['month'])

            if month < 1 or month > 12:
                return self._error_response('Invalid month', 400)

            data = self.db.get_calendar_month(user['id'], year, month)

            return self._json_response({
                'success': True,
                'data': data
            })
        except ValueError:
            return self._error_response('Invalid year or month', 400)
        except Exception as e:
            self.logger.error(f"get_calendar_month error: {e}")
            return self._error_response(str(e), 500)

    async def get_calendar_week(self, request: web.Request) -> web.Response:
        """GET /api/journal/calendar/week/:weekStart - Get week view with entry indicators."""
        try:
            user = await self.auth.get_request_user(request)
            if not user:
                return self._error_response('Authentication required', 401)

            week_start = request.match_info['weekStart']

            # Validate date format
            try:
                datetime.strptime(week_start, '%Y-%m-%d')
            except ValueError:
                return self._error_response('Invalid date format (use YYYY-MM-DD)', 400)

            data = self.db.get_calendar_week(user['id'], week_start)

            return self._json_response({
                'success': True,
                'data': data
            })
        except Exception as e:
            self.logger.error(f"get_calendar_week error: {e}")
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

        # Export/Import
        app.router.add_get('/api/logs/{logId}/export', self.export_trades)
        app.router.add_post('/api/logs/{logId}/import', self.import_trades)

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

        # Journal Entries
        app.router.add_get('/api/journal/entries', self.list_journal_entries)
        app.router.add_get('/api/journal/entries/date/{date}', self.get_journal_entry_by_date)
        app.router.add_get('/api/journal/entries/{id}', self.get_journal_entry)
        app.router.add_post('/api/journal/entries', self.create_journal_entry)
        app.router.add_put('/api/journal/entries/{id}', self.update_journal_entry)
        app.router.add_delete('/api/journal/entries/{id}', self.delete_journal_entry)

        # Journal Retrospectives
        app.router.add_get('/api/journal/retrospectives', self.list_retrospectives)
        app.router.add_get('/api/journal/retrospectives/{type}/{periodStart}', self.get_retrospective_by_period)
        app.router.add_get('/api/journal/retrospectives/{id}', self.get_retrospective)
        app.router.add_post('/api/journal/retrospectives', self.create_retrospective)
        app.router.add_put('/api/journal/retrospectives/{id}', self.update_retrospective)
        app.router.add_delete('/api/journal/retrospectives/{id}', self.delete_retrospective)

        # Journal Trade References
        app.router.add_get('/api/journal/entries/{id}/trades', self.list_entry_trade_refs)
        app.router.add_post('/api/journal/entries/{id}/trades', self.add_entry_trade_ref)
        app.router.add_get('/api/journal/retrospectives/{id}/trades', self.list_retro_trade_refs)
        app.router.add_post('/api/journal/retrospectives/{id}/trades', self.add_retro_trade_ref)
        app.router.add_delete('/api/journal/trade-refs/{id}', self.delete_trade_ref)

        # Journal Attachments
        app.router.add_get('/api/journal/entries/{id}/attachments', self.list_entry_attachments)
        app.router.add_post('/api/journal/entries/{id}/attachments', self.upload_entry_attachment)
        app.router.add_get('/api/journal/retrospectives/{id}/attachments', self.list_retro_attachments)
        app.router.add_post('/api/journal/retrospectives/{id}/attachments', self.upload_retro_attachment)
        app.router.add_get('/api/journal/attachments/{id}', self.download_attachment)
        app.router.add_delete('/api/journal/attachments/{id}', self.delete_attachment)

        # Journal Calendar Views (Temporal Gravity)
        app.router.add_get('/api/journal/calendar/{year}/{month}', self.get_calendar_month)
        app.router.add_get('/api/journal/calendar/week/{weekStart}', self.get_calendar_week)

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
