# services/ml_feedback/circuit_breakers.py
"""Circuit breakers and safety rails for ML trading system."""

from dataclasses import dataclass, asdict, field
from datetime import datetime, date
from typing import Optional, Dict, Any, List
from collections import deque
import numpy as np

from .config import CircuitBreakerConfig, DEFAULT_CONFIG


@dataclass
class Breaker:
    """Individual circuit breaker status."""
    name: str
    triggered: bool
    severity: str = 'warning'  # 'warning' or 'critical'
    message: str = ''
    threshold: Optional[float] = None
    current_value: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BreakerStatus:
    """Overall circuit breaker status."""
    allow_trade: bool
    triggered_breakers: List[Breaker] = field(default_factory=list)
    action: str = 'allow'  # 'allow', 'rules_only', 'block_all'
    checked_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'allow_trade': self.allow_trade,
            'triggered_breakers': [b.to_dict() for b in self.triggered_breakers],
            'action': self.action,
            'checked_at': self.checked_at.isoformat(),
        }


class CircuitBreaker:
    """Hard limits that override ML recommendations.

    Circuit breakers are safety rails that can:
    - Block all trading (critical breakers)
    - Fall back to rules-only scoring (warning breakers)
    - Log anomalies for investigation

    Key breakers:
    - Daily loss limit
    - Max drawdown
    - Order rate limit
    - Slippage anomaly detection
    - Model confidence threshold
    """

    def __init__(self, db=None, config: CircuitBreakerConfig = None):
        self.db = db
        self.config = config or CircuitBreakerConfig()
        self._daily_pnl = 0.0
        self._daily_trades = 0
        self._high_water = 0.0
        self._recent_slippage: deque = deque(maxlen=20)
        self._recent_orders: deque = deque(maxlen=100)  # timestamps
        self._current_regime_confidence = 1.0
        self._ml_enabled = True
        self._last_reset = date.today()

    async def check_all_breakers(self) -> BreakerStatus:
        """Check all breakers before allowing trade."""
        # Reset daily counters if new day
        self._check_daily_reset()

        breakers = [
            self._check_daily_loss_limit(),
            self._check_max_drawdown(),
            self._check_order_rate(),
            self._check_slippage_anomaly(),
            self._check_model_confidence(),
            self._check_ml_kill_switch(),
        ]

        triggered = [b for b in breakers if b.triggered]

        if triggered:
            # Critical breakers block all trading
            if any(b.severity == 'critical' for b in triggered):
                return BreakerStatus(
                    allow_trade=False,
                    triggered_breakers=triggered,
                    action='block_all',
                )
            # Warning breakers fall back to rules-only
            return BreakerStatus(
                allow_trade=True,
                triggered_breakers=triggered,
                action='rules_only',
            )

        return BreakerStatus(allow_trade=True, action='allow')

    def _check_daily_reset(self) -> None:
        """Reset daily counters at start of new day."""
        today = date.today()
        if today != self._last_reset:
            self._daily_pnl = 0.0
            self._daily_trades = 0
            self._last_reset = today

    def _check_daily_loss_limit(self) -> Breaker:
        """Max daily loss limit."""
        if self._daily_pnl < -self.config.max_daily_loss:
            return Breaker(
                name='daily_loss_limit',
                triggered=True,
                severity='critical',
                message=f'Daily P&L ${self._daily_pnl:.2f} exceeds limit -${self.config.max_daily_loss:.2f}',
                threshold=-self.config.max_daily_loss,
                current_value=self._daily_pnl,
            )
        return Breaker(name='daily_loss_limit', triggered=False)

    def _check_max_drawdown(self) -> Breaker:
        """Max drawdown from high water."""
        if self._high_water <= 0:
            return Breaker(name='max_drawdown', triggered=False)

        drawdown_pct = (self._high_water - self._daily_pnl) / self._high_water
        if drawdown_pct > self.config.max_drawdown_pct:
            return Breaker(
                name='max_drawdown',
                triggered=True,
                severity='critical',
                message=f'Drawdown {drawdown_pct:.1%} exceeds limit {self.config.max_drawdown_pct:.1%}',
                threshold=self.config.max_drawdown_pct,
                current_value=drawdown_pct,
            )
        return Breaker(name='max_drawdown', triggered=False)

    def _check_order_rate(self) -> Breaker:
        """Max orders per second."""
        now = datetime.utcnow()

        # Count orders in last second
        recent_count = sum(
            1 for ts in self._recent_orders
            if (now - ts).total_seconds() < 1.0
        )

        if recent_count > self.config.max_orders_per_second:
            return Breaker(
                name='order_rate',
                triggered=True,
                severity='warning',
                message=f'Order rate {recent_count}/s exceeds limit {self.config.max_orders_per_second}/s',
                threshold=self.config.max_orders_per_second,
                current_value=float(recent_count),
            )
        return Breaker(name='order_rate', triggered=False)

    def _check_slippage_anomaly(self) -> Breaker:
        """Detect abnormal slippage."""
        if len(self._recent_slippage) < 10:
            return Breaker(name='slippage_anomaly', triggered=False)

        avg_slippage = np.mean(list(self._recent_slippage))
        if avg_slippage > self.config.slippage_anomaly_threshold:
            return Breaker(
                name='slippage_anomaly',
                triggered=True,
                severity='warning',
                message=f'Avg slippage ${avg_slippage:.2f} exceeds threshold ${self.config.slippage_anomaly_threshold:.2f}',
                threshold=self.config.slippage_anomaly_threshold,
                current_value=avg_slippage,
            )
        return Breaker(name='slippage_anomaly', triggered=False)

    def _check_model_confidence(self) -> Breaker:
        """Don't use ML in low-confidence regimes."""
        if self._current_regime_confidence < self.config.min_regime_confidence:
            return Breaker(
                name='model_confidence',
                triggered=True,
                severity='warning',
                message=f'Regime confidence {self._current_regime_confidence:.2f} below threshold {self.config.min_regime_confidence:.2f}',
                threshold=self.config.min_regime_confidence,
                current_value=self._current_regime_confidence,
            )
        return Breaker(name='model_confidence', triggered=False)

    def _check_ml_kill_switch(self) -> Breaker:
        """One-click disable of ML scoring."""
        if not self._ml_enabled:
            return Breaker(
                name='ml_kill_switch',
                triggered=True,
                severity='warning',
                message='ML scoring manually disabled',
            )
        return Breaker(name='ml_kill_switch', triggered=False)

    # State update methods

    def record_pnl(self, pnl_delta: float) -> None:
        """Record a P&L event."""
        self._daily_pnl += pnl_delta
        if self._daily_pnl > self._high_water:
            self._high_water = self._daily_pnl

    def record_order(self) -> None:
        """Record an order for rate limiting."""
        self._recent_orders.append(datetime.utcnow())

    def record_slippage(self, slippage: float) -> None:
        """Record slippage for anomaly detection."""
        self._recent_slippage.append(slippage)

    def update_regime_confidence(self, confidence: float) -> None:
        """Update current regime confidence."""
        self._current_regime_confidence = confidence

    def disable_ml(self) -> None:
        """Disable ML scoring (kill switch)."""
        self._ml_enabled = False

    def enable_ml(self) -> None:
        """Re-enable ML scoring."""
        self._ml_enabled = True

    def is_ml_enabled(self) -> bool:
        """Check if ML scoring is enabled."""
        return self._ml_enabled

    # Load state from database

    async def load_daily_state(self) -> None:
        """Load daily state from database."""
        if not self.db:
            return

        today = date.today()

        # Get daily P&L from pnl_events
        result = await self.db.fetch_one(
            """SELECT SUM(pnl_delta) as total_pnl
               FROM pnl_events
               WHERE DATE(event_time) = %s""",
            [today]
        )

        if result and result['total_pnl']:
            self._daily_pnl = float(result['total_pnl'])

        # Get high water from daily_performance
        hw_result = await self.db.fetch_one(
            """SELECT MAX(high_water_pnl) as hw
               FROM daily_performance"""
        )

        if hw_result and hw_result['hw']:
            self._high_water = float(hw_result['hw'])

        # Get recent slippage
        slippage_results = await self.db.fetch_all(
            """SELECT slippage FROM pnl_events
               WHERE event_type = 'fill' AND slippage > 0
               ORDER BY event_time DESC
               LIMIT 20"""
        )

        for r in slippage_results:
            self._recent_slippage.append(float(r['slippage']))

    def get_status(self) -> Dict[str, Any]:
        """Get current circuit breaker status."""
        return {
            'daily_pnl': self._daily_pnl,
            'daily_trades': self._daily_trades,
            'high_water': self._high_water,
            'avg_slippage': np.mean(list(self._recent_slippage)) if self._recent_slippage else 0,
            'regime_confidence': self._current_regime_confidence,
            'ml_enabled': self._ml_enabled,
            'limits': {
                'max_daily_loss': self.config.max_daily_loss,
                'max_drawdown_pct': self.config.max_drawdown_pct,
                'max_orders_per_second': self.config.max_orders_per_second,
                'slippage_threshold': self.config.slippage_anomaly_threshold,
                'min_confidence': self.config.min_regime_confidence,
            },
        }

    def reset_daily(self) -> None:
        """Manually reset daily counters."""
        self._daily_pnl = 0.0
        self._daily_trades = 0
        self._last_reset = date.today()
