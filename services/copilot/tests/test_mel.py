"""
MEL Unit Tests - Model Effectiveness Layer testing.
"""

import pytest
from datetime import datetime
from ..intel.mel_models import (
    MELModelScore,
    MELSnapshot,
    MELDelta,
    MELConfig,
    ModelState,
    Trend,
    Confidence,
    CoherenceState,
    Session,
)
from ..intel.mel_calculator import MELCalculator, DummyCalculator
from ..intel.mel import MELOrchestrator


class TestMELModels:
    """Test MEL data models."""

    def test_model_score_creation(self):
        """Test creating a MELModelScore."""
        score = MELModelScore(
            effectiveness=82.5,
            trend=Trend.IMPROVING,
            state=ModelState.VALID,
            confidence=Confidence.HIGH,
            detail={"level_respect_rate": 79.0},
        )

        assert score.effectiveness == 82.5
        assert score.trend == Trend.IMPROVING
        assert score.state == ModelState.VALID
        assert score.confidence == Confidence.HIGH
        assert score.detail["level_respect_rate"] == 79.0

    def test_model_score_to_dict(self):
        """Test serialization."""
        score = MELModelScore(
            effectiveness=65.0,
            trend=Trend.STABLE,
            state=ModelState.DEGRADED,
            confidence=Confidence.MEDIUM,
            detail={},
        )

        data = score.to_dict()

        assert data["effectiveness"] == 65.0
        assert data["trend"] == "stable"
        assert data["state"] == "DEGRADED"
        assert data["confidence"] == "medium"

    def test_model_score_from_dict(self):
        """Test deserialization."""
        data = {
            "effectiveness": 45.0,
            "trend": "degrading",
            "state": "REVOKED",
            "confidence": "low",
            "detail": {"note": "test"},
        }

        score = MELModelScore.from_dict(data)

        assert score.effectiveness == 45.0
        assert score.trend == Trend.DEGRADING
        assert score.state == ModelState.REVOKED
        assert score.confidence == Confidence.LOW

    def test_mel_delta(self):
        """Test MEL delta calculation."""
        delta = MELDelta(
            gamma_effectiveness=2.5,
            volume_profile_effectiveness=-1.2,
            global_integrity=-0.09,
        )

        data = delta.to_dict()

        assert data["gamma_effectiveness"] == 2.5
        assert data["volume_profile_effectiveness"] == -1.2


class TestMELConfig:
    """Test MEL configuration."""

    def test_default_config(self):
        """Test default configuration values."""
        config = MELConfig()

        assert config.valid_threshold == 70.0
        assert config.degraded_threshold == 50.0
        assert config.weights["gamma"] == 0.30
        assert config.weights["volume_profile"] == 0.25
        assert config.coherence_multipliers["STABLE"] == 1.0
        assert config.coherence_multipliers["COLLAPSING"] == 0.60

    def test_custom_config(self):
        """Test custom configuration."""
        config = MELConfig(
            valid_threshold=80.0,
            degraded_threshold=60.0,
        )

        assert config.valid_threshold == 80.0
        assert config.degraded_threshold == 60.0


class TestDummyCalculator:
    """Test placeholder calculator."""

    def test_dummy_returns_neutral(self):
        """Dummy calculator should return neutral score."""
        config = MELConfig()
        calc = DummyCalculator("test_model", config)

        score = calc.calculate_score({})

        assert score.effectiveness == 65.0
        assert score.detail.get("implemented") is False


class TestMELOrchestrator:
    """Test MEL orchestrator."""

    def test_orchestrator_creation(self):
        """Test creating orchestrator."""
        config = MELConfig()
        mel = MELOrchestrator(config=config)

        assert mel.config == config
        assert len(mel._calculators) == 5  # gamma, vp, liq, vol, session

    def test_state_determination(self):
        """Test state determination from effectiveness."""
        config = MELConfig()
        calc = DummyCalculator("test", config)

        assert calc._determine_state(80) == ModelState.VALID
        assert calc._determine_state(70) == ModelState.VALID
        assert calc._determine_state(69) == ModelState.DEGRADED
        assert calc._determine_state(50) == ModelState.DEGRADED
        assert calc._determine_state(49) == ModelState.REVOKED
        assert calc._determine_state(0) == ModelState.REVOKED

    def test_global_integrity_calculation(self):
        """Test global integrity weighted calculation."""
        config = MELConfig()
        mel = MELOrchestrator(config=config)

        # Create scores
        gamma = MELModelScore(80, Trend.STABLE, ModelState.VALID, Confidence.HIGH, {})
        vp = MELModelScore(70, Trend.STABLE, ModelState.VALID, Confidence.HIGH, {})
        liq = MELModelScore(60, Trend.STABLE, ModelState.DEGRADED, Confidence.MEDIUM, {})
        vol = MELModelScore(50, Trend.STABLE, ModelState.DEGRADED, Confidence.MEDIUM, {})
        session = MELModelScore(70, Trend.STABLE, ModelState.VALID, Confidence.HIGH, {})

        integrity = mel._calculate_global_integrity(
            gamma, vp, liq, vol, session, CoherenceState.STABLE
        )

        # Manual calculation: 0.30*80 + 0.25*70 + 0.20*60 + 0.15*50 + 0.10*70 = 67.0
        # With STABLE multiplier (1.0) = 67.0
        assert abs(integrity - 67.0) < 0.1


class TestMELSnapshot:
    """Test snapshot functionality."""

    def test_snapshot_state_summary(self):
        """Test compact state summary."""
        snapshot = MELSnapshot(
            timestamp_utc=datetime.utcnow(),
            snapshot_id="test_001",
            session=Session.RTH,
            event_flags=[],
            gamma=MELModelScore(84, Trend.IMPROVING, ModelState.VALID, Confidence.HIGH, {}),
            volume_profile=MELModelScore(62, Trend.STABLE, ModelState.DEGRADED, Confidence.MEDIUM, {}),
            liquidity=MELModelScore(35, Trend.DEGRADING, ModelState.REVOKED, Confidence.MEDIUM, {}),
            volatility=MELModelScore(28, Trend.DEGRADING, ModelState.REVOKED, Confidence.LOW, {}),
            session_structure=MELModelScore(57, Trend.STABLE, ModelState.DEGRADED, Confidence.MEDIUM, {}),
            cross_model_coherence=33,
            coherence_state=CoherenceState.COLLAPSING,
            global_structure_integrity=42,
        )

        summary = snapshot.get_state_summary()

        assert "MEL:42%" in summary
        assert "Γ:84✓" in summary
        assert "VP:62⚠" in summary
        assert "LIQ:35✗" in summary

    def test_snapshot_serialization(self):
        """Test snapshot to_dict and from_dict."""
        original = MELSnapshot(
            timestamp_utc=datetime(2026, 1, 30, 12, 0, 0),
            snapshot_id="test_002",
            session=Session.RTH,
            event_flags=["FOMC"],
            gamma=MELModelScore(80, Trend.STABLE, ModelState.VALID, Confidence.HIGH, {}),
            volume_profile=MELModelScore(70, Trend.STABLE, ModelState.VALID, Confidence.HIGH, {}),
            liquidity=MELModelScore(60, Trend.STABLE, ModelState.DEGRADED, Confidence.MEDIUM, {}),
            volatility=MELModelScore(55, Trend.STABLE, ModelState.DEGRADED, Confidence.MEDIUM, {}),
            session_structure=MELModelScore(65, Trend.STABLE, ModelState.DEGRADED, Confidence.MEDIUM, {}),
            cross_model_coherence=70,
            coherence_state=CoherenceState.MIXED,
            global_structure_integrity=68,
            delta=MELDelta(gamma_effectiveness=1.5, global_integrity=0.5),
        )

        data = original.to_dict()
        restored = MELSnapshot.from_dict(data)

        assert restored.snapshot_id == original.snapshot_id
        assert restored.session == original.session
        assert restored.event_flags == original.event_flags
        assert restored.gamma.effectiveness == original.gamma.effectiveness
        assert restored.global_structure_integrity == original.global_structure_integrity


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
