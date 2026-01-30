"""
MEL Calculator Unit Tests - Testing individual model effectiveness calculators.
"""

import pytest
from datetime import datetime
from ..intel.mel_models import MELConfig, ModelState, Confidence
from ..intel.mel_gamma import GammaEffectivenessCalculator
from ..intel.mel_volume_profile import VolumeProfileEffectivenessCalculator, AuctionState
from ..intel.mel_liquidity import LiquidityEffectivenessCalculator
from ..intel.mel_volatility import VolatilityEffectivenessCalculator
from ..intel.mel_session import SessionEffectivenessCalculator
from ..intel.mel_coherence import CoherenceCalculator, CoherenceState


class TestGammaCalculator:
    """Test gamma effectiveness calculator."""

    @pytest.fixture
    def calculator(self):
        config = MELConfig()
        return GammaEffectivenessCalculator(config=config)

    def test_calculator_name(self, calculator):
        """Test calculator returns correct name."""
        assert calculator.model_name == "gamma"

    def test_insufficient_data_returns_neutral(self, calculator):
        """With no data, should return neutral score."""
        score = calculator.calculate_score({})
        assert 60 <= score.effectiveness <= 70
        assert "Insufficient data" in score.detail.get("note", "")

    def test_with_sample_data(self, calculator):
        """Test with sample market data."""
        market_data = {
            "gamma_levels": [
                {"strike": 6000, "gex": 1000000},
                {"strike": 6050, "gex": -500000},
            ],
            "zero_gamma": 6025,
            "gamma_magnet": 6020,
            "price_history": [
                {"close": 6015, "high": 6020, "low": 6010},
                {"close": 6018, "high": 6025, "low": 6015},
                {"close": 6022, "high": 6028, "low": 6018},
                {"close": 6020, "high": 6024, "low": 6016},
                {"close": 6019, "high": 6022, "low": 6017},
            ],
        }

        score = calculator.calculate_score(market_data)

        assert 0 <= score.effectiveness <= 100
        assert score.state in [ModelState.VALID, ModelState.DEGRADED, ModelState.REVOKED]
        assert "level_respect_rate" in score.detail
        assert "mean_reversion_success" in score.detail


class TestVolumeProfileCalculator:
    """Test volume profile effectiveness calculator."""

    @pytest.fixture
    def calculator(self):
        config = MELConfig()
        return VolumeProfileEffectivenessCalculator(config=config)

    def test_calculator_name(self, calculator):
        """Test calculator returns correct name."""
        assert calculator.model_name == "volume_profile"

    def test_insufficient_data_returns_neutral(self, calculator):
        """With no data, should return neutral score."""
        score = calculator.calculate_score({})
        assert 60 <= score.effectiveness <= 70

    def test_with_sample_data(self, calculator):
        """Test with sample market data."""
        market_data = {
            "poc": 6020,
            "vah": 6040,
            "val": 6000,
            "hvns": [6020, 6010],
            "lvns": [6030, 6005],
            "price_history": [
                {"close": 6015, "high": 6020, "low": 6010},
                {"close": 6018, "high": 6025, "low": 6015},
                {"close": 6022, "high": 6028, "low": 6018},
                {"close": 6020, "high": 6024, "low": 6016},
                {"close": 6019, "high": 6022, "low": 6017},
                {"close": 6025, "high": 6030, "low": 6020},
                {"close": 6028, "high": 6032, "low": 6024},
                {"close": 6022, "high": 6028, "low": 6018},
            ],
        }

        score = calculator.calculate_score(market_data)

        assert 0 <= score.effectiveness <= 100
        assert "hvn_acceptance" in score.detail
        assert "lvn_rejection" in score.detail
        assert "rotation_completion" in score.detail
        assert "auction_state" in score.detail

    def test_auction_state_enum(self):
        """Test AuctionState enum values."""
        assert AuctionState.BALANCE.value == "balance"
        assert AuctionState.INITIATIVE_UP.value == "initiative_up"
        assert AuctionState.ROTATION.value == "rotation"


class TestLiquidityCalculator:
    """Test liquidity effectiveness calculator."""

    @pytest.fixture
    def calculator(self):
        config = MELConfig()
        return LiquidityEffectivenessCalculator(config=config)

    def test_calculator_name(self, calculator):
        """Test calculator returns correct name."""
        assert calculator.model_name == "liquidity"

    def test_insufficient_data_returns_neutral(self, calculator):
        """With no data, should return neutral score."""
        score = calculator.calculate_score({})
        assert 60 <= score.effectiveness <= 70

    def test_with_spread_data(self, calculator):
        """Test with bid/ask spread data."""
        market_data = {
            "bid_ask_spread": 0.10,
            "avg_spread": 0.08,
            "bid_size": 500,
            "ask_size": 400,
            "price_history": [
                {"close": 6015, "price": 6015},
                {"close": 6018, "price": 6018},
                {"close": 6022, "price": 6022},
            ],
        }

        score = calculator.calculate_score(market_data)

        assert 0 <= score.effectiveness <= 100
        assert "slippage_state" in score.detail
        assert "imbalance_utility" in score.detail
        assert "liquidity_state" in score.detail


class TestVolatilityCalculator:
    """Test volatility effectiveness calculator."""

    @pytest.fixture
    def calculator(self):
        config = MELConfig()
        return VolatilityEffectivenessCalculator(config=config)

    def test_calculator_name(self, calculator):
        """Test calculator returns correct name."""
        assert calculator.model_name == "volatility"

    def test_insufficient_data_returns_neutral(self, calculator):
        """With no data, should return neutral score."""
        score = calculator.calculate_score({})
        assert 60 <= score.effectiveness <= 70

    def test_with_iv_rv_data(self, calculator):
        """Test with IV/RV data."""
        market_data = {
            "iv_atm": 18.5,
            "realized_vol": 16.2,
            "vix": 17.0,
            "vol_regime": "normal",
            "price_history": [
                {"close": 6015},
                {"close": 6018},
                {"close": 6022},
            ],
        }

        score = calculator.calculate_score(market_data)

        assert 0 <= score.effectiveness <= 100
        assert "iv_rv_ratio" in score.detail
        assert "current_regime" in score.detail

    def test_iv_rv_alignment_scoring(self, calculator):
        """Test IV/RV alignment scoring."""
        # Perfect alignment
        assert calculator._score_iv_rv_alignment(1.0) > 85

        # Good alignment
        assert calculator._score_iv_rv_alignment(1.1) > 75

        # Poor alignment
        assert calculator._score_iv_rv_alignment(2.0) < 30


class TestSessionCalculator:
    """Test session effectiveness calculator."""

    @pytest.fixture
    def calculator(self):
        config = MELConfig()
        return SessionEffectivenessCalculator(config=config)

    def test_calculator_name(self, calculator):
        """Test calculator returns correct name."""
        assert calculator.model_name == "session"

    def test_insufficient_data_returns_neutral(self, calculator):
        """With no data, should return neutral score."""
        score = calculator.calculate_score({})
        assert 60 <= score.effectiveness <= 70

    def test_session_phase_detection(self, calculator):
        """Test session phase detection."""
        from datetime import time

        # Pre-market
        pre_market = datetime(2026, 1, 30, 8, 0, 0)
        assert calculator._determine_current_phase(pre_market) == "pre_market"

        # Open discovery
        open_phase = datetime(2026, 1, 30, 10, 0, 0)
        assert calculator._determine_current_phase(open_phase) == "open_discovery"

        # Midday balance
        midday = datetime(2026, 1, 30, 12, 30, 0)
        assert calculator._determine_current_phase(midday) == "midday_balance"

        # Late session
        late = datetime(2026, 1, 30, 15, 0, 0)
        assert calculator._determine_current_phase(late) == "late_session"


class TestCoherenceCalculator:
    """Test cross-model coherence calculator."""

    @pytest.fixture
    def calculator(self):
        config = MELConfig()
        return CoherenceCalculator(config=config)

    def test_all_valid_models_stable(self, calculator):
        """All VALID models should produce STABLE coherence."""
        from ..intel.mel_models import MELModelScore, Trend

        gamma = MELModelScore(80, Trend.STABLE, ModelState.VALID, Confidence.HIGH, {})
        vp = MELModelScore(75, Trend.STABLE, ModelState.VALID, Confidence.HIGH, {})
        liq = MELModelScore(72, Trend.STABLE, ModelState.VALID, Confidence.MEDIUM, {})
        vol = MELModelScore(78, Trend.STABLE, ModelState.VALID, Confidence.MEDIUM, {})
        session = MELModelScore(77, Trend.STABLE, ModelState.VALID, Confidence.HIGH, {})

        coherence, state, detail = calculator.calculate_coherence(
            gamma, vp, liq, vol, session
        )

        assert state == CoherenceState.STABLE
        assert coherence > 70

    def test_multiple_revoked_collapsing(self, calculator):
        """Multiple REVOKED models should produce COLLAPSING coherence."""
        from ..intel.mel_models import MELModelScore, Trend

        gamma = MELModelScore(80, Trend.STABLE, ModelState.VALID, Confidence.HIGH, {})
        vp = MELModelScore(35, Trend.DEGRADING, ModelState.REVOKED, Confidence.LOW, {})
        liq = MELModelScore(30, Trend.DEGRADING, ModelState.REVOKED, Confidence.LOW, {})
        vol = MELModelScore(25, Trend.DEGRADING, ModelState.REVOKED, Confidence.LOW, {})
        session = MELModelScore(45, Trend.DEGRADING, ModelState.REVOKED, Confidence.LOW, {})

        coherence, state, detail = calculator.calculate_coherence(
            gamma, vp, liq, vol, session
        )

        assert state == CoherenceState.COLLAPSING

    def test_mixed_states_mixed(self, calculator):
        """Mix of states should produce MIXED coherence."""
        from ..intel.mel_models import MELModelScore, Trend

        gamma = MELModelScore(80, Trend.STABLE, ModelState.VALID, Confidence.HIGH, {})
        vp = MELModelScore(65, Trend.STABLE, ModelState.DEGRADED, Confidence.MEDIUM, {})
        liq = MELModelScore(55, Trend.STABLE, ModelState.DEGRADED, Confidence.MEDIUM, {})
        vol = MELModelScore(72, Trend.STABLE, ModelState.VALID, Confidence.MEDIUM, {})
        session = MELModelScore(60, Trend.STABLE, ModelState.DEGRADED, Confidence.MEDIUM, {})

        coherence, state, detail = calculator.calculate_coherence(
            gamma, vp, liq, vol, session
        )

        assert state == CoherenceState.MIXED

    def test_asymmetry_detection(self, calculator):
        """Test asymmetric structure detection."""
        from ..intel.mel_models import MELModelScore, Trend

        # One working, others failed
        gamma = MELModelScore(85, Trend.STABLE, ModelState.VALID, Confidence.HIGH, {})
        vp = MELModelScore(30, Trend.DEGRADING, ModelState.REVOKED, Confidence.LOW, {})
        liq = MELModelScore(25, Trend.DEGRADING, ModelState.REVOKED, Confidence.LOW, {})
        vol = MELModelScore(28, Trend.DEGRADING, ModelState.REVOKED, Confidence.LOW, {})
        session = MELModelScore(32, Trend.DEGRADING, ModelState.REVOKED, Confidence.LOW, {})

        coherence, state, detail = calculator.calculate_coherence(
            gamma, vp, liq, vol, session
        )

        assert detail["asymmetric_structure"] == "Severe"


class TestCalculatorBaseClass:
    """Test base calculator functionality."""

    def test_normalize_score(self):
        """Test score normalization."""
        config = MELConfig()
        calc = GammaEffectivenessCalculator(config=config)

        assert calc.normalize_score(150) == 100
        assert calc.normalize_score(-10) == 0
        assert calc.normalize_score(50) == 50

    def test_calculate_rate(self):
        """Test rate calculation."""
        config = MELConfig()
        calc = GammaEffectivenessCalculator(config=config)

        assert calc.calculate_rate(7, 10) == 70.0
        assert calc.calculate_rate(0, 0, default=50.0) == 50.0
        assert calc.calculate_rate(10, 10) == 100.0

    def test_score_categorical(self):
        """Test categorical scoring."""
        config = MELConfig()
        calc = GammaEffectivenessCalculator(config=config)

        scoring = {"High": 90, "Medium": 60, "Low": 30}

        assert calc.score_categorical("High", scoring) == 90
        assert calc.score_categorical("Unknown", scoring, default=50) == 50

    def test_weighted_average(self):
        """Test weighted average calculation."""
        config = MELConfig()
        calc = GammaEffectivenessCalculator(config=config)

        scores = [(80, 0.3), (60, 0.4), (70, 0.3)]
        avg = calc.weighted_average(scores)

        # 0.3*80 + 0.4*60 + 0.3*70 = 24 + 24 + 21 = 69
        assert abs(avg - 69) < 0.1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
