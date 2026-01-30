# services/journal/intel/analytics_v2.py
"""Log-scoped analytics for the FOTW Trade Log system (v2)."""

from typing import List, Dict, Any, Optional
from datetime import datetime

from .models_v2 import LogAnalytics, EquityPoint, DrawdownPoint
from .db_v2 import JournalDBv2


class AnalyticsV2:
    """Log-scoped performance analytics calculator."""

    def __init__(self, db: JournalDBv2):
        self.db = db

    def get_full_analytics(self, log_id: str) -> Optional[LogAnalytics]:
        """
        Calculate full performance analytics for a trade log.

        Covers all 5 FOTW reporting categories:
        1. Time & Scale
        2. Capital & Returns
        3. Win/Loss Distribution
        4. Risk & Asymmetry
        5. System Health
        """
        log = self.db.get_log(log_id)
        if not log:
            return None

        stats = self.db.get_log_stats(log_id)
        if not stats:
            return LogAnalytics(log_id=log_id, log_name=log.name)

        analytics = LogAnalytics(
            log_id=log_id,
            log_name=log.name,
            starting_capital=log.starting_capital
        )

        # 1. Time & Scale
        analytics.total_trades = stats['total_trades']
        if stats['first_trade'] and stats['last_trade']:
            try:
                first = datetime.fromisoformat(stats['first_trade'].replace('Z', '+00:00'))
                last = datetime.fromisoformat(stats['last_trade'].replace('Z', '+00:00'))
                analytics.span_days = max(1, (last - first).days)
                weeks = analytics.span_days / 7
                if weeks > 0:
                    analytics.trades_per_week = stats['total_trades'] / weeks
            except (ValueError, AttributeError):
                analytics.span_days = 0

        # 2. Capital & Returns
        analytics.net_profit = stats['total_pnl']
        analytics.current_equity = log.starting_capital + analytics.net_profit
        if log.starting_capital > 0:
            analytics.total_return_percent = (analytics.net_profit / log.starting_capital) * 100

        # 3. Win/Loss Distribution
        analytics.open_trades = stats['open_trades']
        analytics.closed_trades = stats['closed_trades']
        analytics.winners = stats['winners']
        analytics.losers = stats['losers']
        analytics.breakeven = stats['breakeven']

        if analytics.closed_trades > 0:
            analytics.win_rate = (analytics.winners / analytics.closed_trades) * 100

        analytics.avg_win = int(stats['avg_win']) if stats['avg_win'] else 0
        analytics.avg_loss = int(stats['avg_loss']) if stats['avg_loss'] else 0

        if analytics.avg_loss and analytics.avg_loss != 0:
            analytics.win_loss_ratio = abs(analytics.avg_win / analytics.avg_loss)

        # 4. Risk & Asymmetry
        analytics.avg_risk = int(stats['avg_risk']) if stats['avg_risk'] else 0
        analytics.largest_win = stats['largest_win']
        analytics.largest_loss = stats['largest_loss']

        gross_profit = stats['gross_profit']
        gross_loss = stats['gross_loss']

        # Store gross profit/loss
        analytics.gross_profit = gross_profit
        analytics.gross_loss = gross_loss

        if gross_profit > 0 and analytics.largest_win:
            analytics.largest_win_pct_gross = (analytics.largest_win / gross_profit) * 100
        if gross_loss > 0 and analytics.largest_loss:
            analytics.largest_loss_pct_gross = (abs(analytics.largest_loss) / gross_loss) * 100

        # Average net profit per trade
        if analytics.closed_trades > 0:
            analytics.avg_net_profit = int(analytics.net_profit / analytics.closed_trades)

        # 5. System Health
        if gross_loss > 0:
            analytics.profit_factor = gross_profit / gross_loss

        analytics.avg_r_multiple = stats['avg_r_multiple'] or 0

        # Calculate max drawdown from equity curve
        analytics.max_drawdown_pct = self._calculate_max_drawdown(log_id, log.starting_capital)

        # Calculate average R2R and Sharpe ratio
        analytics.avg_r2r = self._calculate_avg_r2r(log_id)
        analytics.sharpe_ratio = self._calculate_sharpe_ratio(log_id, log.starting_capital)

        return analytics

    def _calculate_max_drawdown(self, log_id: str, starting_capital: int) -> float:
        """Calculate maximum drawdown percentage from peak."""
        trades = self.db.get_closed_trades_for_equity(log_id)
        if not trades:
            return 0.0

        equity = starting_capital
        peak = equity
        max_dd_pct = 0.0

        for trade in trades:
            if trade.pnl is not None:
                equity += trade.pnl
                if equity > peak:
                    peak = equity
                if peak > 0:
                    dd_pct = ((peak - equity) / peak) * 100
                    if dd_pct > max_dd_pct:
                        max_dd_pct = dd_pct

        return max_dd_pct

    def _calculate_avg_r2r(self, log_id: str) -> float:
        """Calculate average reward-to-risk ratio (max_profit / entry_cost)."""
        trades = self.db.list_trades(log_id=log_id, limit=10000)
        if not trades:
            return 0.0

        # Multiplier lookup
        multipliers = {
            'SPX': 100, 'NDX': 100, 'XSP': 100, 'SPY': 100,
            'ES': 50, 'MES': 50, 'NQ': 20, 'MNQ': 20,
        }

        r2r_values = []
        for trade in trades:
            if trade.max_profit and trade.max_profit > 0 and trade.entry_price > 0:
                multiplier = multipliers.get(trade.symbol.upper(), 100)
                cost = trade.entry_price * multiplier * trade.quantity
                if cost > 0:
                    r2r = trade.max_profit / cost
                    r2r_values.append(r2r)

        if not r2r_values:
            return 0.0

        return sum(r2r_values) / len(r2r_values)

    def _calculate_sharpe_ratio(self, log_id: str, starting_capital: int) -> float:
        """
        Calculate Sharpe ratio.
        Sharpe = mean(returns) / std(returns) * sqrt(252) for daily returns
        We'll use per-trade returns for simplicity.
        """
        import math

        trades = self.db.list_trades(log_id=log_id, status='closed', limit=10000)
        if len(trades) < 2:
            return 0.0

        # Calculate per-trade returns as percentage of starting capital
        returns = []
        for trade in trades:
            if trade.pnl is not None and starting_capital > 0:
                ret = trade.pnl / starting_capital
                returns.append(ret)

        if len(returns) < 2:
            return 0.0

        # Mean return
        mean_ret = sum(returns) / len(returns)

        # Standard deviation
        variance = sum((r - mean_ret) ** 2 for r in returns) / len(returns)
        std_ret = math.sqrt(variance)

        if std_ret == 0:
            return 0.0

        # Annualize: assume ~252 trading days, estimate trades per day
        # For simplicity, use sqrt(trades_per_year) approximation
        # A typical active trader might do 1-5 trades per day
        # We'll use a simple annualization factor
        sharpe = (mean_ret / std_ret) * math.sqrt(len(returns))

        return sharpe

    def get_equity_curve(
        self,
        log_id: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None
    ) -> List[EquityPoint]:
        """Generate equity curve data points for a log."""
        log = self.db.get_log(log_id)
        if not log:
            return []

        trades = self.db.get_closed_trades_for_equity(log_id, from_date, to_date)

        if not trades:
            return []

        equity_points: List[EquityPoint] = []
        cumulative_pnl = 0

        # Add starting point at 0 (relative to starting capital)
        first_trade = trades[0]
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

    def get_drawdown_curve(
        self,
        log_id: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None
    ) -> List[DrawdownPoint]:
        """Generate drawdown curve data points for a log."""
        log = self.db.get_log(log_id)
        if not log:
            return []

        trades = self.db.get_closed_trades_for_equity(log_id, from_date, to_date)

        if not trades:
            return []

        drawdown_points: List[DrawdownPoint] = []
        equity = log.starting_capital
        peak = equity

        # Add starting point at 0% drawdown
        first_trade = trades[0]
        start_time = first_trade.exit_time or first_trade.entry_time
        drawdown_points.append(DrawdownPoint(
            time=start_time,
            drawdown_pct=0.0,
            peak=peak,
            current=equity
        ))

        for trade in trades:
            if trade.pnl is not None:
                equity += trade.pnl

                # Update peak
                if equity > peak:
                    peak = equity

                # Calculate drawdown percentage
                dd_pct = 0.0
                if peak > 0:
                    dd_pct = ((peak - equity) / peak) * 100

                drawdown_points.append(DrawdownPoint(
                    time=trade.exit_time or trade.entry_time,
                    drawdown_pct=dd_pct,
                    peak=peak,
                    current=equity
                ))

        return drawdown_points

    def get_strategy_breakdown(
        self,
        log_id: str
    ) -> Dict[str, Dict[str, Any]]:
        """Get performance breakdown by strategy type for a log."""
        trades = self.db.list_trades(log_id=log_id, status='closed', limit=10000)

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

    def get_daily_pnl(
        self,
        log_id: str,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """Get daily P&L breakdown for the last N days."""
        trades = self.db.get_closed_trades_for_equity(log_id)

        daily_pnl: Dict[str, int] = {}
        for trade in trades:
            if trade.exit_time and trade.pnl is not None:
                try:
                    date_str = trade.exit_time[:10]  # YYYY-MM-DD
                    daily_pnl[date_str] = daily_pnl.get(date_str, 0) + trade.pnl
                except (ValueError, IndexError):
                    continue

        result = []
        for date_str in sorted(daily_pnl.keys()):
            result.append({
                'date': date_str,
                'pnl': daily_pnl[date_str],
                'pnl_dollars': daily_pnl[date_str] / 100
            })

        return result[-days:]

    def get_time_analysis(
        self,
        log_id: str
    ) -> Dict[str, Any]:
        """Analyze performance by time (hour of day, day of week)."""
        trades = self.db.list_trades(log_id=log_id, status='closed', limit=10000)

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

    def get_r_multiple_distribution(
        self,
        log_id: str
    ) -> Dict[str, Any]:
        """Analyze R-multiple distribution for a log."""
        trades = self.db.list_trades(log_id=log_id, status='closed', limit=10000)

        r_multiples = []
        for trade in trades:
            if trade.r_multiple is not None:
                r_multiples.append(trade.r_multiple)

        if not r_multiples:
            return {
                'count': 0,
                'avg': 0,
                'median': 0,
                'positive': 0,
                'negative': 0,
                'above_1r': 0,
                'above_2r': 0,
                'below_minus_1r': 0
            }

        r_multiples.sort()
        count = len(r_multiples)
        median_idx = count // 2

        return {
            'count': count,
            'avg': sum(r_multiples) / count,
            'median': r_multiples[median_idx],
            'positive': sum(1 for r in r_multiples if r > 0),
            'negative': sum(1 for r in r_multiples if r < 0),
            'above_1r': sum(1 for r in r_multiples if r >= 1.0),
            'above_2r': sum(1 for r in r_multiples if r >= 2.0),
            'below_minus_1r': sum(1 for r in r_multiples if r <= -1.0)
        }
