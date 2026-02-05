# services/ml_feedback/pnl_ledger.py
"""Append-only P&L event ledger for accurate path reconstruction."""

from dataclasses import dataclass, asdict
from datetime import datetime, date
from typing import Optional, Dict, Any, List
from decimal import Decimal


@dataclass
class PnLEvent:
    """A P&L event (always delta, never cumulative)."""
    event_time: datetime
    idea_id: str
    trade_id: Optional[str]
    strategy_id: Optional[str]
    pnl_delta: float
    fees: float
    slippage: float
    underlying_price: float
    event_type: str  # 'mark', 'fill', 'settlement', 'adjustment'

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EquityCurvePoint:
    """A point on the equity curve."""
    timestamp: datetime
    cumulative_pnl: float
    high_water: float
    drawdown: float
    drawdown_pct: float


class PnLLedger:
    """Append-only P&L event ledger.

    Key properties:
    - Append-only: Events are never modified or deleted
    - Path-dependent: Full history of P&L changes is preserved
    - Reconstructable: Cumulative P&L at any point can be computed
    """

    def __init__(self, db=None):
        self.db = db

    async def record_event(
        self,
        idea_id: str,
        pnl_delta: float,
        underlying_price: float,
        event_type: str,
        trade_id: Optional[str] = None,
        strategy_id: Optional[str] = None,
        fees: float = 0.0,
        slippage: float = 0.0,
    ) -> int:
        """Record a P&L event. Returns event ID."""
        if not self.db:
            return 0

        event = PnLEvent(
            event_time=datetime.utcnow(),
            idea_id=idea_id,
            trade_id=trade_id,
            strategy_id=strategy_id,
            pnl_delta=pnl_delta,
            fees=fees,
            slippage=slippage,
            underlying_price=underlying_price,
            event_type=event_type,
        )

        result = await self.db.execute(
            """INSERT INTO pnl_events
               (event_time, idea_id, trade_id, strategy_id,
                pnl_delta, fees, slippage, underlying_price, event_type)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            [
                event.event_time,
                event.idea_id,
                event.trade_id,
                event.strategy_id,
                event.pnl_delta,
                event.fees,
                event.slippage,
                event.underlying_price,
                event.event_type,
            ]
        )
        return result.lastrowid if result else 0

    async def record_mark(
        self,
        idea_id: str,
        pnl_delta: float,
        underlying_price: float,
        trade_id: Optional[str] = None,
    ) -> int:
        """Record a mark-to-market event."""
        return await self.record_event(
            idea_id=idea_id,
            pnl_delta=pnl_delta,
            underlying_price=underlying_price,
            event_type='mark',
            trade_id=trade_id,
        )

    async def record_fill(
        self,
        idea_id: str,
        pnl_delta: float,
        underlying_price: float,
        trade_id: str,
        fees: float = 0.0,
        slippage: float = 0.0,
    ) -> int:
        """Record a fill event."""
        return await self.record_event(
            idea_id=idea_id,
            pnl_delta=pnl_delta,
            underlying_price=underlying_price,
            event_type='fill',
            trade_id=trade_id,
            fees=fees,
            slippage=slippage,
        )

    async def record_settlement(
        self,
        idea_id: str,
        pnl_delta: float,
        underlying_price: float,
        trade_id: Optional[str] = None,
    ) -> int:
        """Record a settlement event."""
        return await self.record_event(
            idea_id=idea_id,
            pnl_delta=pnl_delta,
            underlying_price=underlying_price,
            event_type='settlement',
            trade_id=trade_id,
        )

    async def get_events_for_idea(self, idea_id: str) -> List[Dict[str, Any]]:
        """Get all P&L events for an idea."""
        if not self.db:
            return []

        return await self.db.fetch_all(
            """SELECT * FROM pnl_events
               WHERE idea_id = %s
               ORDER BY event_time ASC""",
            [idea_id]
        )

    async def get_cumulative_pnl(self, idea_id: str) -> float:
        """Get cumulative P&L for an idea."""
        if not self.db:
            return 0.0

        result = await self.db.fetch_one(
            """SELECT SUM(pnl_delta) as total_pnl
               FROM pnl_events
               WHERE idea_id = %s""",
            [idea_id]
        )
        return float(result['total_pnl'] or 0) if result else 0.0

    async def get_daily_pnl(self, target_date: date) -> Dict[str, Any]:
        """Get aggregated P&L for a specific date."""
        if not self.db:
            return {}

        result = await self.db.fetch_one(
            """SELECT
                 SUM(pnl_delta) as net_pnl,
                 SUM(pnl_delta + fees + slippage) as gross_pnl,
                 SUM(fees) as total_fees,
                 SUM(slippage) as total_slippage,
                 COUNT(DISTINCT idea_id) as trade_count,
                 SUM(CASE WHEN pnl_delta > 0 THEN 1 ELSE 0 END) as win_count,
                 SUM(CASE WHEN pnl_delta < 0 THEN 1 ELSE 0 END) as loss_count
               FROM pnl_events
               WHERE DATE(event_time) = %s""",
            [target_date]
        )
        return dict(result) if result else {}

    async def compute_equity_curve(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[EquityCurvePoint]:
        """Compute equity curve from P&L events."""
        if not self.db:
            return []

        query = """SELECT event_time, pnl_delta
                   FROM pnl_events
                   WHERE 1=1"""
        params = []

        if start_date:
            query += " AND DATE(event_time) >= %s"
            params.append(start_date)
        if end_date:
            query += " AND DATE(event_time) <= %s"
            params.append(end_date)

        query += " ORDER BY event_time ASC"

        events = await self.db.fetch_all(query, params)

        curve = []
        cumulative_pnl = 0.0
        high_water = 0.0

        for event in events:
            cumulative_pnl += float(event['pnl_delta'])
            high_water = max(high_water, cumulative_pnl)
            drawdown = high_water - cumulative_pnl
            drawdown_pct = drawdown / high_water if high_water > 0 else 0.0

            curve.append(EquityCurvePoint(
                timestamp=event['event_time'],
                cumulative_pnl=cumulative_pnl,
                high_water=high_water,
                drawdown=drawdown,
                drawdown_pct=drawdown_pct,
            ))

        return curve

    async def get_max_drawdown(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, float]:
        """Calculate maximum drawdown metrics."""
        curve = await self.compute_equity_curve(start_date, end_date)

        if not curve:
            return {'max_drawdown': 0.0, 'max_drawdown_pct': 0.0}

        max_drawdown = max(p.drawdown for p in curve)
        max_drawdown_pct = max(p.drawdown_pct for p in curve)

        return {
            'max_drawdown': max_drawdown,
            'max_drawdown_pct': max_drawdown_pct,
        }

    async def materialize_daily_performance(self, target_date: date) -> int:
        """Materialize daily performance record.

        Returns the daily_performance record ID.
        """
        if not self.db:
            return 0

        # Get daily metrics
        daily = await self.get_daily_pnl(target_date)
        if not daily or daily.get('net_pnl') is None:
            return 0

        # Get cumulative high water up to this date
        curve = await self.compute_equity_curve(end_date=target_date)
        high_water = curve[-1].high_water if curve else 0.0
        max_dd = await self.get_max_drawdown(end_date=target_date)

        # Get primary model used this day
        model_info = await self.db.fetch_one(
            """SELECT model_id, COUNT(*) as cnt
               FROM ml_decisions
               WHERE DATE(decision_time) = %s AND model_id IS NOT NULL
               GROUP BY model_id
               ORDER BY cnt DESC
               LIMIT 1""",
            [target_date]
        )

        # Calculate ML contribution percentage
        ml_stats = await self.db.fetch_one(
            """SELECT
                 COUNT(*) as total,
                 SUM(CASE WHEN ml_score IS NOT NULL THEN 1 ELSE 0 END) as ml_count
               FROM ml_decisions
               WHERE DATE(decision_time) = %s""",
            [target_date]
        )
        ml_contribution = 0.0
        if ml_stats and ml_stats['total'] > 0:
            ml_contribution = ml_stats['ml_count'] / ml_stats['total']

        # Upsert daily performance record
        result = await self.db.execute(
            """INSERT INTO daily_performance
               (date, net_pnl, gross_pnl, total_fees,
                high_water_pnl, max_drawdown, drawdown_pct,
                trade_count, win_count, loss_count,
                primary_model_id, ml_contribution_pct)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE
                 net_pnl = VALUES(net_pnl),
                 gross_pnl = VALUES(gross_pnl),
                 total_fees = VALUES(total_fees),
                 high_water_pnl = VALUES(high_water_pnl),
                 max_drawdown = VALUES(max_drawdown),
                 drawdown_pct = VALUES(drawdown_pct),
                 trade_count = VALUES(trade_count),
                 win_count = VALUES(win_count),
                 loss_count = VALUES(loss_count),
                 primary_model_id = VALUES(primary_model_id),
                 ml_contribution_pct = VALUES(ml_contribution_pct)""",
            [
                target_date,
                daily.get('net_pnl', 0),
                daily.get('gross_pnl', 0),
                daily.get('total_fees', 0),
                high_water,
                max_dd['max_drawdown'],
                max_dd['max_drawdown_pct'],
                daily.get('trade_count', 0),
                daily.get('win_count', 0),
                daily.get('loss_count', 0),
                model_info['model_id'] if model_info else None,
                ml_contribution,
            ]
        )
        return result.lastrowid if result else 0

    async def get_recent_slippage(self, count: int = 20) -> List[float]:
        """Get recent slippage values for anomaly detection."""
        if not self.db:
            return []

        results = await self.db.fetch_all(
            """SELECT slippage FROM pnl_events
               WHERE event_type = 'fill' AND slippage > 0
               ORDER BY event_time DESC
               LIMIT %s""",
            [count]
        )
        return [float(r['slippage']) for r in results]
