"""
ADI Orchestrator - AI Data Interface snapshot generation.

"Screens are for humans. Data is for machines."

The ADI Orchestrator aggregates market data from various sources
into the canonical AIStructureSnapshot format.
"""

import logging
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from collections import deque

from .adi_models import (
    AIStructureSnapshot,
    PriceState,
    VolatilityState,
    GammaStructure,
    AuctionStructure,
    Microstructure,
    SessionContext,
    MELScores,
    ADIDelta,
    UserContext,
    generate_snapshot_id,
    SCHEMA_VERSION,
)
from .mel import MELOrchestrator
from .mel_models import MELSnapshot


class ADIOrchestrator:
    """
    AI Data Interface orchestrator.

    Aggregates market state from multiple sources into canonical snapshots.
    """

    def __init__(
        self,
        mel_orchestrator: Optional[MELOrchestrator] = None,
        market_data_provider: Optional[Callable[[], Dict[str, Any]]] = None,
        user_context_provider: Optional[Callable[[], Dict[str, Any]]] = None,
        logger: Optional[logging.Logger] = None,
        symbol: str = "SPX",
    ):
        self.mel = mel_orchestrator
        self.market_data_provider = market_data_provider
        self.user_context_provider = user_context_provider
        self.logger = logger or logging.getLogger("ADI")
        self.symbol = symbol

        # Snapshot history
        self._history: deque = deque(maxlen=500)
        self._last_snapshot: Optional[AIStructureSnapshot] = None

    def generate_snapshot(
        self,
        include_user_context: bool = False,
    ) -> AIStructureSnapshot:
        """
        Generate a complete ADI snapshot.

        Aggregates data from:
        - Market data provider (price, gamma, volume profile)
        - MEL orchestrator (model effectiveness scores)
        - User context provider (selected tile, alerts, trades)
        """
        now = datetime.utcnow()

        # Get market data
        market_data = {}
        if self.market_data_provider:
            market_data = self.market_data_provider()

        # Get MEL snapshot
        mel_snapshot = None
        if self.mel:
            mel_snapshot = self.mel.get_current_snapshot()

        # Get user context if requested
        user_context = None
        if include_user_context and self.user_context_provider:
            user_ctx_data = self.user_context_provider()
            user_context = self._build_user_context(user_ctx_data)

        # Build snapshot sections
        snapshot = AIStructureSnapshot(
            timestamp_utc=now,
            symbol=self.symbol,
            session=self._determine_session(now),
            dte=market_data.get("dte"),
            event_flags=self._get_event_flags(market_data, mel_snapshot),
            schema_version=SCHEMA_VERSION,
            snapshot_id=generate_snapshot_id(),
            price_state=self._build_price_state(market_data),
            volatility_state=self._build_volatility_state(market_data),
            gamma_structure=self._build_gamma_structure(market_data),
            auction_structure=self._build_auction_structure(market_data),
            microstructure=self._build_microstructure(market_data),
            session_context=self._build_session_context(now, market_data),
            mel_scores=self._build_mel_scores(mel_snapshot),
            delta=self._calculate_delta(market_data, mel_snapshot),
            user_context=user_context,
        )

        # Update history
        self._history.append(snapshot)
        self._last_snapshot = snapshot

        return snapshot

    def _build_price_state(self, market_data: Dict[str, Any]) -> PriceState:
        """Build price state from market data."""
        spot = market_data.get("spot_price")
        vwap = market_data.get("vwap")

        return PriceState(
            spot_price=spot,
            session_high=market_data.get("session_high"),
            session_low=market_data.get("session_low"),
            vwap=vwap,
            distance_from_vwap=(spot - vwap) if spot and vwap else None,
            intraday_range=market_data.get("intraday_range"),
            realized_vol_intra=market_data.get("realized_vol_intra"),
        )

    def _build_volatility_state(self, market_data: Dict[str, Any]) -> VolatilityState:
        """Build volatility state from market data."""
        iv = market_data.get("iv_atm")
        rv = market_data.get("realized_vol")

        return VolatilityState(
            call_iv_atm=market_data.get("call_iv_atm") or iv,
            put_iv_atm=market_data.get("put_iv_atm") or iv,
            iv_skew=market_data.get("iv_skew"),
            iv_rv_ratio=(iv / rv) if iv and rv and rv > 0 else None,
            vol_regime=market_data.get("vol_regime"),
        )

    def _build_gamma_structure(self, market_data: Dict[str, Any]) -> GammaStructure:
        """Build gamma structure from market data."""
        gamma_levels = market_data.get("gamma_levels", [])

        # Extract high gamma strikes
        high_gamma_strikes = []
        if gamma_levels:
            sorted_levels = sorted(gamma_levels, key=lambda x: abs(x.get("gex", 0)), reverse=True)
            high_gamma_strikes = [l.get("strike") for l in sorted_levels[:5] if l.get("strike")]

        return GammaStructure(
            net_gex=market_data.get("net_gex"),
            zero_gamma_level=market_data.get("zero_gamma"),
            active_gamma_magnet=market_data.get("gamma_magnet"),
            gex_ratio=market_data.get("gex_ratio"),
            call_gamma_total=market_data.get("call_gamma_total"),
            put_gamma_total=market_data.get("put_gamma_total"),
            high_gamma_strikes=high_gamma_strikes,
            gamma_flip_level=market_data.get("gamma_flip"),
        )

    def _build_auction_structure(self, market_data: Dict[str, Any]) -> AuctionStructure:
        """Build auction structure from market data."""
        return AuctionStructure(
            poc=market_data.get("poc"),
            value_area_high=market_data.get("vah"),
            value_area_low=market_data.get("val"),
            rotation_state=market_data.get("rotation_state"),
            auction_state=market_data.get("auction_state"),
            hvns=market_data.get("hvns", []),
            lvns=market_data.get("lvns", []),
        )

    def _build_microstructure(self, market_data: Dict[str, Any]) -> Microstructure:
        """Build microstructure from market data."""
        bid = market_data.get("bid_size", 0)
        ask = market_data.get("ask_size", 0)
        total = bid + ask

        imbalance = None
        if total > 0:
            imbalance = (bid - ask) / total

        return Microstructure(
            bid_ask_imbalance=imbalance,
            aggressive_flow=market_data.get("aggressive_flow"),
            absorption_detected=market_data.get("absorption_detected"),
            sweep_detected=market_data.get("sweep_detected"),
            liquidity_state=market_data.get("liquidity_state"),
        )

    def _build_session_context(self, now: datetime, market_data: Dict[str, Any]) -> SessionContext:
        """Build session context."""
        # RTH: 9:30 AM - 4:00 PM ET (simplified)
        rth_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
        rth_close = now.replace(hour=16, minute=0, second=0, microsecond=0)

        is_rth = rth_open <= now <= rth_close
        minutes_since_open = None
        minutes_to_close = None

        if is_rth:
            minutes_since_open = int((now - rth_open).total_seconds() / 60)
            minutes_to_close = int((rth_close - now).total_seconds() / 60)

        # Determine session phase
        phase = "pre_market"
        if is_rth:
            if minutes_since_open < 60:
                phase = "open"
            elif minutes_to_close > 90:
                phase = "midday"
            else:
                phase = "late"
        elif now > rth_close:
            phase = "after_hours"

        return SessionContext(
            minutes_since_open=minutes_since_open,
            minutes_to_close=minutes_to_close,
            session_phase=phase,
            is_rth=is_rth,
            day_of_week=now.strftime("%A"),
        )

    def _build_mel_scores(self, mel_snapshot: Optional[MELSnapshot]) -> MELScores:
        """Build MEL scores from MEL snapshot."""
        if not mel_snapshot:
            return MELScores()

        return MELScores(
            gamma_effectiveness=mel_snapshot.gamma.effectiveness,
            gamma_state=mel_snapshot.gamma.state.value,
            volume_profile_effectiveness=mel_snapshot.volume_profile.effectiveness,
            volume_profile_state=mel_snapshot.volume_profile.state.value,
            liquidity_effectiveness=mel_snapshot.liquidity.effectiveness,
            liquidity_state=mel_snapshot.liquidity.state.value,
            volatility_effectiveness=mel_snapshot.volatility.effectiveness,
            volatility_state=mel_snapshot.volatility.state.value,
            session_effectiveness=mel_snapshot.session_structure.effectiveness,
            session_state=mel_snapshot.session_structure.state.value,
            global_structure_integrity=mel_snapshot.global_structure_integrity,
            coherence_state=mel_snapshot.coherence_state.value,
        )

    def _build_user_context(self, ctx_data: Dict[str, Any]) -> UserContext:
        """Build user context from provider data."""
        return UserContext(
            selected_tile=ctx_data.get("selected_tile"),
            risk_graph_strategies=ctx_data.get("risk_graph_strategies", []),
            active_alerts=ctx_data.get("active_alerts", []),
            open_trades=ctx_data.get("open_trades", []),
            active_log_id=ctx_data.get("active_log_id"),
        )

    def _calculate_delta(
        self,
        market_data: Dict[str, Any],
        mel_snapshot: Optional[MELSnapshot],
    ) -> Optional[ADIDelta]:
        """Calculate delta from previous snapshot."""
        if not self._last_snapshot:
            return None

        last = self._last_snapshot
        current_spot = market_data.get("spot_price")
        current_gex = market_data.get("net_gex")
        current_zero_gamma = market_data.get("zero_gamma")
        current_integrity = mel_snapshot.global_structure_integrity if mel_snapshot else None

        return ADIDelta(
            spot_price=(current_spot - last.price_state.spot_price)
                if current_spot and last.price_state.spot_price else None,
            net_gex=(current_gex - last.gamma_structure.net_gex)
                if current_gex and last.gamma_structure.net_gex else None,
            zero_gamma=(current_zero_gamma - last.gamma_structure.zero_gamma_level)
                if current_zero_gamma and last.gamma_structure.zero_gamma_level else None,
            global_integrity=(current_integrity - last.mel_scores.global_structure_integrity)
                if current_integrity and last.mel_scores.global_structure_integrity else None,
        )

    def _get_event_flags(
        self,
        market_data: Dict[str, Any],
        mel_snapshot: Optional[MELSnapshot],
    ) -> List[str]:
        """Collect event flags from all sources."""
        flags = list(market_data.get("event_flags", []))

        if mel_snapshot:
            flags.extend(mel_snapshot.event_flags)

        return list(set(flags))  # Dedupe

    def _determine_session(self, now: datetime) -> str:
        """Determine current market session."""
        hour = now.hour

        if 9 <= hour <= 16:
            return "RTH"
        elif 4 <= hour <= 9 or 16 <= hour <= 20:
            return "ETH"
        else:
            return "GLOBEX"

    # ========== Query Methods ==========

    def get_current_snapshot(self) -> Optional[AIStructureSnapshot]:
        """Get most recent ADI snapshot."""
        return self._last_snapshot

    def get_history(
        self,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[AIStructureSnapshot]:
        """Get snapshot history."""
        snapshots = list(self._history)

        if since:
            snapshots = [s for s in snapshots if s.timestamp_utc >= since]

        return snapshots[-limit:]
