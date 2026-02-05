# services/ml_feedback/feature_extractor.py
"""Feature extraction with versioning for point-in-time correctness."""

from dataclasses import dataclass, asdict
from datetime import datetime, time
from typing import Dict, Any, Optional, List
import math

from .config import (
    FEATURE_SET_VERSION,
    FEATURE_EXTRACTOR_VERSION,
    GEX_CALC_VERSION,
    VIX_REGIME_CLASSIFIER_VERSION,
    DEFAULT_CONFIG,
)


@dataclass
class MarketSnapshot:
    """A snapshot of market data at a point in time."""
    spot: float
    vix: float
    vix3m: float = 0.0

    # Intraday range
    day_high: Optional[float] = None
    day_low: Optional[float] = None

    # Historical prices for returns
    spot_history: Optional[Dict[str, float]] = None  # keyed by minutes ago

    # GEX structure
    gex_total: Optional[float] = None
    gex_call_wall: Optional[float] = None
    gex_put_wall: Optional[float] = None
    gex_gamma_flip: Optional[float] = None

    # Market mode
    market_mode: Optional[str] = None
    bias_lfi: Optional[float] = None
    bias_direction: Optional[str] = None

    # Cross-asset
    es_futures_premium: Optional[float] = None
    tnx_level: Optional[float] = None
    dxy_level: Optional[float] = None


@dataclass
class TradeIdea:
    """A trade idea to be scored."""
    id: str
    symbol: str
    strategy: str  # single, vertical, butterfly
    side: str  # call, put
    strike: float
    width: Optional[int] = None
    dte: int = 0
    debit: float = 0.0
    score: float = 0.0  # Original rule-based score


@dataclass
class FeatureVector:
    """Complete feature vector for ML inference."""
    # Metadata
    idea_id: str
    snapshot_time: str
    feature_set_version: str
    feature_extractor_version: str
    gex_calc_version: Optional[str]
    vix_regime_classifier_version: Optional[str]

    # Price Action
    spot_price: float
    spot_5m_return: Optional[float] = None
    spot_15m_return: Optional[float] = None
    spot_1h_return: Optional[float] = None
    spot_1d_return: Optional[float] = None
    range_position: Optional[float] = None

    # Volatility
    vix_level: Optional[float] = None
    vix_regime: Optional[str] = None
    vix_term_slope: Optional[float] = None
    iv_rank_30d: Optional[float] = None
    iv_percentile_30d: Optional[float] = None

    # GEX Structure
    gex_total: Optional[float] = None
    gex_call_wall: Optional[float] = None
    gex_put_wall: Optional[float] = None
    gex_gamma_flip: Optional[float] = None
    spot_vs_call_wall: Optional[float] = None
    spot_vs_put_wall: Optional[float] = None
    spot_vs_gamma_flip: Optional[float] = None

    # Market Mode
    market_mode: Optional[str] = None
    bias_lfi: Optional[float] = None
    bias_direction: Optional[str] = None

    # Time
    minutes_since_open: Optional[int] = None
    day_of_week: Optional[int] = None
    is_opex_week: bool = False
    days_to_monthly_opex: Optional[int] = None

    # Strategy
    strategy_type: Optional[str] = None
    side: Optional[str] = None
    dte: Optional[int] = None
    width: Optional[int] = None
    strike_vs_spot: Optional[float] = None
    original_score: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    def to_model_input(self, feature_list: List[str]) -> List[float]:
        """Convert to ordered list for model input."""
        d = self.to_dict()
        result = []
        for feature in feature_list:
            val = d.get(feature)
            if val is None:
                result.append(0.0)
            elif isinstance(val, bool):
                result.append(1.0 if val else 0.0)
            elif isinstance(val, str):
                # Encode categorical features
                result.append(self._encode_categorical(feature, val))
            else:
                result.append(float(val))
        return result

    def _encode_categorical(self, feature: str, value: str) -> float:
        """Encode categorical features as numeric."""
        encodings = {
            'vix_regime': {
                'chaos': 3.0,
                'goldilocks_2': 2.0,
                'goldilocks_1': 1.0,
                'zombieland': 0.0,
            },
            'bias_direction': {
                'bullish': 1.0,
                'neutral': 0.0,
                'bearish': -1.0,
            },
            'strategy_type': {
                'single': 1.0,
                'vertical': 2.0,
                'butterfly': 3.0,
            },
            'side': {
                'call': 1.0,
                'put': -1.0,
            },
        }
        return encodings.get(feature, {}).get(value, 0.0)


class FeatureExtractor:
    """Extract ML features from market data at idea generation time."""

    def __init__(self, config=None):
        self.config = config or DEFAULT_CONFIG
        self.version = FEATURE_SET_VERSION

    def extract_features(
        self,
        idea: TradeIdea,
        market_data: MarketSnapshot
    ) -> FeatureVector:
        """Extract all features for an idea."""
        now = datetime.utcnow()

        features = FeatureVector(
            idea_id=idea.id,
            snapshot_time=now.isoformat(),
            feature_set_version=FEATURE_SET_VERSION,
            feature_extractor_version=FEATURE_EXTRACTOR_VERSION,
            gex_calc_version=GEX_CALC_VERSION if market_data.gex_total else None,
            vix_regime_classifier_version=VIX_REGIME_CLASSIFIER_VERSION,
            spot_price=market_data.spot,
        )

        # Price action features
        self._extract_price_action(features, market_data)

        # Volatility features
        self._extract_volatility(features, market_data)

        # GEX structure features
        self._extract_gex_structure(features, market_data)

        # Market mode features
        self._extract_market_mode(features, market_data)

        # Time features
        self._extract_time_features(features, now)

        # Strategy features
        self._extract_strategy_features(features, idea, market_data.spot)

        return features

    def _extract_price_action(
        self,
        features: FeatureVector,
        market_data: MarketSnapshot
    ) -> None:
        """Extract price action features."""
        spot = market_data.spot
        history = market_data.spot_history or {}

        # Returns
        if '5' in history:
            features.spot_5m_return = (spot - history['5']) / history['5']
        if '15' in history:
            features.spot_15m_return = (spot - history['15']) / history['15']
        if '60' in history:
            features.spot_1h_return = (spot - history['60']) / history['60']
        if '1440' in history:  # 24 hours
            features.spot_1d_return = (spot - history['1440']) / history['1440']

        # Range position
        if market_data.day_high and market_data.day_low:
            day_range = market_data.day_high - market_data.day_low
            if day_range > 0:
                features.range_position = (spot - market_data.day_low) / day_range

    def _extract_volatility(
        self,
        features: FeatureVector,
        market_data: MarketSnapshot
    ) -> None:
        """Extract volatility features."""
        features.vix_level = market_data.vix
        features.vix_regime = self._classify_vix_regime(market_data.vix)

        if market_data.vix3m and market_data.vix:
            features.vix_term_slope = (market_data.vix3m - market_data.vix) / market_data.vix

        # IV rank/percentile would require historical IV data
        # Leaving as None for now - can be populated by caller

    def _classify_vix_regime(self, vix: float) -> str:
        """Classify VIX into regime."""
        thresholds = self.config.vix_thresholds
        if vix >= thresholds['chaos']:
            return 'chaos'
        elif vix >= thresholds['goldilocks_2_lower']:
            return 'goldilocks_2'
        elif vix >= thresholds['goldilocks_1_lower']:
            return 'goldilocks_1'
        else:
            return 'zombieland'

    def _extract_gex_structure(
        self,
        features: FeatureVector,
        market_data: MarketSnapshot
    ) -> None:
        """Extract GEX structure features."""
        spot = market_data.spot

        features.gex_total = market_data.gex_total
        features.gex_call_wall = market_data.gex_call_wall
        features.gex_put_wall = market_data.gex_put_wall
        features.gex_gamma_flip = market_data.gex_gamma_flip

        # Relative positions
        if market_data.gex_call_wall:
            features.spot_vs_call_wall = (market_data.gex_call_wall - spot) / spot
        if market_data.gex_put_wall:
            features.spot_vs_put_wall = (spot - market_data.gex_put_wall) / spot
        if market_data.gex_gamma_flip:
            features.spot_vs_gamma_flip = (market_data.gex_gamma_flip - spot) / spot

    def _extract_market_mode(
        self,
        features: FeatureVector,
        market_data: MarketSnapshot
    ) -> None:
        """Extract market mode features."""
        features.market_mode = market_data.market_mode
        features.bias_lfi = market_data.bias_lfi
        features.bias_direction = market_data.bias_direction

    def _extract_time_features(
        self,
        features: FeatureVector,
        now: datetime
    ) -> None:
        """Extract time-based features."""
        # Market hours (EST)
        market_open = time(9, 30)
        current_time = now.time()

        # Minutes since open
        if current_time >= market_open:
            open_dt = datetime.combine(now.date(), market_open)
            features.minutes_since_open = int((now - open_dt).total_seconds() / 60)

        # Day of week (0=Monday, 4=Friday)
        features.day_of_week = now.weekday()

        # OpEx week detection
        features.is_opex_week = self._is_opex_week(now)
        features.days_to_monthly_opex = self._days_to_monthly_opex(now)

    def _is_opex_week(self, dt: datetime) -> bool:
        """Check if date is in monthly OpEx week (third Friday of month)."""
        # Find third Friday of month
        third_friday = self._get_third_friday(dt.year, dt.month)
        week_start = third_friday.replace(day=third_friday.day - 4)  # Monday
        week_end = third_friday.replace(day=third_friday.day)
        return week_start <= dt.date() <= week_end

    def _get_third_friday(self, year: int, month: int) -> 'datetime.date':
        """Get the third Friday of a month."""
        from datetime import date, timedelta

        # Find first Friday
        first_day = date(year, month, 1)
        days_until_friday = (4 - first_day.weekday()) % 7
        first_friday = first_day + timedelta(days=days_until_friday)

        # Third Friday is 14 days later
        return first_friday + timedelta(days=14)

    def _days_to_monthly_opex(self, dt: datetime) -> int:
        """Calculate days until next monthly OpEx."""
        from datetime import timedelta

        third_friday = self._get_third_friday(dt.year, dt.month)

        if dt.date() > third_friday:
            # Move to next month
            if dt.month == 12:
                third_friday = self._get_third_friday(dt.year + 1, 1)
            else:
                third_friday = self._get_third_friday(dt.year, dt.month + 1)

        return (third_friday - dt.date()).days

    def _extract_strategy_features(
        self,
        features: FeatureVector,
        idea: TradeIdea,
        spot: float
    ) -> None:
        """Extract strategy-specific features."""
        features.strategy_type = idea.strategy
        features.side = idea.side
        features.dte = idea.dte
        features.width = idea.width
        features.original_score = idea.score

        if spot > 0:
            features.strike_vs_spot = (idea.strike - spot) / spot

    def extract_market_context(
        self,
        market_data: MarketSnapshot
    ) -> Dict[str, Any]:
        """Extract market context for caching (shared across ideas)."""
        return {
            'spot_price': market_data.spot,
            'vix_level': market_data.vix,
            'vix_regime': self._classify_vix_regime(market_data.vix),
            'gex_total': market_data.gex_total,
            'spot_vs_call_wall': (market_data.gex_call_wall - market_data.spot) / market_data.spot if market_data.gex_call_wall else None,
            'spot_vs_put_wall': (market_data.spot - market_data.gex_put_wall) / market_data.spot if market_data.gex_put_wall else None,
            'market_mode': market_data.market_mode,
            'bias_direction': market_data.bias_direction,
        }
