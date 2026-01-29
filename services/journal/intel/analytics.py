# services/journal/intel/analytics.py
"""Analytics calculations for the journal service."""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from .models import Trade, AnalyticsSummary, EquityPoint
from .db import JournalDB


class Analytics:
    """Performance analytics calculator."""

    def __init__(self, db: JournalDB):
        self.db = db

    def get_summary(
        self,
        user_id: str = "default",
        from_date: Optional[str] = None,
        to_date: Optional[str] = None
    ) -> AnalyticsSummary:
        """Calculate performance summary statistics."""
        # Get basic stats from DB
        stats = self.db.get_stats(user_id)

        summary = AnalyticsSummary(
            total_trades=stats['total_trades'],
            open_trades=stats['open_trades'],
            closed_trades=stats['closed_trades'],
            winners=stats['winners'],
            losers=stats['losers'],
            breakeven=stats['breakeven'],
            total_pnl=stats['total_pnl'],
            largest_win=stats['largest_win'],
            largest_loss=stats['largest_loss'],
            avg_win=stats['avg_win'],
            avg_loss=stats['avg_loss'],
        )

        # Calculate derived metrics
        if summary.closed_trades > 0:
            summary.win_rate = (summary.winners / summary.closed_trades) * 100
            summary.avg_trade = summary.total_pnl / summary.closed_trades

        # Profit factor = gross profit / gross loss
        if stats['gross_loss'] > 0:
            summary.profit_factor = stats['gross_profit'] / stats['gross_loss']

        return summary

    def get_equity_curve(
        self,
        user_id: str = "default",
        from_date: Optional[str] = None,
        to_date: Optional[str] = None
    ) -> List[EquityPoint]:
        """Generate equity curve data points."""
        trades = self.db.get_closed_trades_for_equity(user_id, from_date, to_date)

        if not trades:
            return []

        # Build cumulative equity curve
        equity_points: List[EquityPoint] = []
        cumulative_pnl = 0.0

        # Add starting point at 0
        if trades:
            first_trade = trades[0]
            # Start point just before first trade
            start_time = first_trade.exit_time or first_trade.entry_time
            equity_points.append(EquityPoint(time=start_time, value=0))

        for trade in trades:
            if trade.pnl is not None:
                cumulative_pnl += trade.pnl
                equity_points.append(EquityPoint(
                    time=trade.exit_time or trade.entry_time,
                    value=cumulative_pnl,
                    trade_id=trade.id
                ))

        return equity_points

    def get_daily_pnl(
        self,
        user_id: str = "default",
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """Get daily P&L breakdown for the last N days."""
        trades = self.db.get_closed_trades_for_equity(user_id)

        # Group by date
        daily_pnl: Dict[str, float] = {}
        for trade in trades:
            if trade.exit_time and trade.pnl is not None:
                # Parse date from ISO format
                try:
                    date_str = trade.exit_time[:10]  # YYYY-MM-DD
                    daily_pnl[date_str] = daily_pnl.get(date_str, 0) + trade.pnl
                except (ValueError, IndexError):
                    continue

        # Convert to list of points
        result = []
        for date_str in sorted(daily_pnl.keys()):
            result.append({
                'date': date_str,
                'pnl': daily_pnl[date_str]
            })

        # Limit to last N days
        return result[-days:]

    def get_strategy_breakdown(
        self,
        user_id: str = "default"
    ) -> Dict[str, Dict[str, Any]]:
        """Get performance breakdown by strategy type."""
        trades = self.db.list_trades(user_id=user_id, status='closed', limit=10000)

        breakdown: Dict[str, Dict[str, Any]] = {}

        for trade in trades:
            strat = trade.strategy
            if strat not in breakdown:
                breakdown[strat] = {
                    'count': 0,
                    'winners': 0,
                    'losers': 0,
                    'total_pnl': 0,
                    'avg_pnl': 0,
                    'win_rate': 0
                }

            b = breakdown[strat]
            b['count'] += 1
            b['total_pnl'] += trade.pnl or 0

            if trade.pnl is not None:
                if trade.pnl > 0:
                    b['winners'] += 1
                elif trade.pnl < 0:
                    b['losers'] += 1

        # Calculate averages
        for strat, b in breakdown.items():
            if b['count'] > 0:
                b['avg_pnl'] = b['total_pnl'] / b['count']
                closed = b['winners'] + b['losers']
                if closed > 0:
                    b['win_rate'] = (b['winners'] / closed) * 100

        return breakdown

    def get_time_analysis(
        self,
        user_id: str = "default"
    ) -> Dict[str, Any]:
        """Analyze performance by time (hour of day, day of week)."""
        trades = self.db.list_trades(user_id=user_id, status='closed', limit=10000)

        by_hour: Dict[int, Dict[str, Any]] = {}
        by_day: Dict[int, Dict[str, Any]] = {}

        for trade in trades:
            if not trade.entry_time or trade.pnl is None:
                continue

            try:
                dt = datetime.fromisoformat(trade.entry_time.replace('Z', '+00:00'))
                hour = dt.hour
                day = dt.weekday()  # 0=Monday

                # By hour
                if hour not in by_hour:
                    by_hour[hour] = {'count': 0, 'pnl': 0}
                by_hour[hour]['count'] += 1
                by_hour[hour]['pnl'] += trade.pnl

                # By day
                if day not in by_day:
                    by_day[day] = {'count': 0, 'pnl': 0}
                by_day[day]['count'] += 1
                by_day[day]['pnl'] += trade.pnl

            except (ValueError, AttributeError):
                continue

        return {
            'by_hour': by_hour,
            'by_day': by_day
        }
