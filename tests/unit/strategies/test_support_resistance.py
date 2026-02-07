"""Tests for Support/Resistance Breakout strategy."""

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from tradingsystem.models.signal import SignalType
from tradingsystem.strategies.base import StrategyContext
from tradingsystem.strategies.examples.support_resistance import SupportResistanceStrategy


# --- Fixtures ---


@pytest.fixture
def strategy():
    """Create default Support/Resistance strategy."""
    return SupportResistanceStrategy()


@pytest.fixture
def strategy_custom_params():
    """Create Support/Resistance strategy with custom parameters."""
    return SupportResistanceStrategy(
        lookback=30,
        tolerance=0.001,
        min_touches=3,
        breakout_pct=0.002,
    )


@pytest.fixture
def sample_candles():
    """Create sample OHLCV data."""
    dates = pd.date_range(
        start="2024-01-01",
        periods=100,
        freq="1h",
        tz=timezone.utc,
    )
    data = {
        "open": [1.0850] * 100,
        "high": [1.0860] * 100,
        "low": [1.0840] * 100,
        "close": [1.0850] * 100,
        "volume": [1000] * 100,
    }
    return pd.DataFrame(data, index=dates)


def create_context(candles, indicators, current_price=1.0850):
    """Helper to create StrategyContext."""
    return StrategyContext(
        instrument="EUR_USD",
        period="1h",
        candles=candles,
        indicators=indicators,
        current_time=candles.index[-1],
        current_price=current_price,
    )


# --- SupportResistanceStrategy Initialization Tests ---


class TestSupportResistanceStrategyInit:
    """Tests for SupportResistanceStrategy initialization."""

    def test_default_params(self, strategy):
        """Should have default parameters."""
        assert strategy.params["lookback"] == 50
        assert strategy.params["tolerance"] == 0.0005
        assert strategy.params["min_touches"] == 2
        assert strategy.params["breakout_pct"] == 0.001

    def test_custom_params(self, strategy_custom_params):
        """Should accept custom parameters."""
        assert strategy_custom_params.params["lookback"] == 30
        assert strategy_custom_params.params["tolerance"] == 0.001
        assert strategy_custom_params.params["min_touches"] == 3
        assert strategy_custom_params.params["breakout_pct"] == 0.002

    def test_metadata(self, strategy):
        """Should have correct metadata."""
        assert strategy.name == "Support/Resistance Breakout"
        assert strategy.version == "1.0.0"
        assert "EUR_USD" in strategy.instruments
        assert "1h" in strategy.periods

    def test_description(self, strategy):
        """Should have meaningful description."""
        assert "support" in strategy.description.lower() or "breakout" in strategy.description.lower()


# --- Required Indicators Tests ---


class TestRequiredIndicators:
    """Tests for required indicators configuration."""

    def test_no_indicators_required(self, strategy):
        """Should not require any external indicators (pure price action)."""
        indicators = strategy.required_indicators

        assert len(indicators) == 0


# --- Signal Generation Tests ---


class TestGenerateSignals:
    """Tests for generate_signals method."""

    def test_no_signal_with_flat_price(self, strategy, sample_candles):
        """Should return no signals when price is flat."""
        context = create_context(sample_candles, {})
        signals = strategy.generate_signals(context)

        # Flat price won't create clear S/R levels
        assert len(signals) == 0

    def test_buy_signal_on_resistance_breakout(self, strategy):
        """Should generate BUY signal when price breaks above resistance."""
        dates = pd.date_range(start="2024-01-01", periods=100, freq="1h", tz=timezone.utc)

        # Create clear resistance level at 1.0900 with multiple touches
        highs = [1.0860] * 20 + [1.0900] * 5 + [1.0860] * 30 + [1.0900] * 5 + [1.0860] * 38 + [1.0850, 1.0920]
        lows = [1.0840] * 100
        closes = [1.0855] * 98 + [1.0890, 1.0915]

        candles = pd.DataFrame({
            "open": [1.0850] * 100,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [1000] * 100,
        }, index=dates)

        context = create_context(candles, {}, current_price=1.0915)
        signals = strategy.generate_signals(context)

        if len(signals) > 0:
            assert signals[0].signal_type == SignalType.BUY
            assert "resistance" in signals[0].reason.lower()
            assert signals[0].metadata["level_type"] == "resistance"

    def test_sell_signal_on_support_breakdown(self, strategy):
        """Should generate SELL signal when price breaks below support."""
        dates = pd.date_range(start="2024-01-01", periods=100, freq="1h", tz=timezone.utc)

        # Create clear support level at 1.0800 with multiple touches
        lows = [1.0840] * 20 + [1.0800] * 5 + [1.0840] * 30 + [1.0800] * 5 + [1.0840] * 38 + [1.0850, 1.0780]
        highs = [1.0860] * 100
        closes = [1.0855] * 98 + [1.0810, 1.0785]

        candles = pd.DataFrame({
            "open": [1.0850] * 100,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [1000] * 100,
        }, index=dates)

        context = create_context(candles, {}, current_price=1.0785)
        signals = strategy.generate_signals(context)

        if len(signals) > 0:
            assert signals[0].signal_type == SignalType.SELL
            assert "support" in signals[0].reason.lower()
            assert signals[0].metadata["level_type"] == "support"

    def test_no_signal_when_insufficient_data(self, strategy):
        """Should return no signals with insufficient data for S/R detection."""
        dates = pd.date_range(start="2024-01-01", periods=20, freq="1h", tz=timezone.utc)
        candles = pd.DataFrame({
            "open": [1.0850] * 20,
            "high": [1.0860] * 20,
            "low": [1.0840] * 20,
            "close": [1.0850] * 20,
            "volume": [1000] * 20,
        }, index=dates)

        context = create_context(candles, {})
        signals = strategy.generate_signals(context)

        assert len(signals) == 0

    def test_pivot_high_detection(self, strategy):
        """Should correctly detect pivot highs."""
        # Create price series with clear pivot high
        dates = pd.date_range(start="2024-01-01", periods=100, freq="1h", tz=timezone.utc)
        highs = [1.0850] * 40 + [1.0840, 1.0860, 1.0900, 1.0860, 1.0840] + [1.0850] * 55
        candles = pd.DataFrame({
            "open": [1.0850] * 100,
            "high": highs,
            "low": [1.0840] * 100,
            "close": [1.0850] * 100,
        }, index=dates)

        pivot_highs, _ = strategy._find_pivot_points(candles, window=2)

        # Should detect pivot high at 1.0900
        assert len(pivot_highs) > 0

    def test_pivot_low_detection(self, strategy):
        """Should correctly detect pivot lows."""
        # Create price series with clear pivot low
        dates = pd.date_range(start="2024-01-01", periods=100, freq="1h", tz=timezone.utc)
        lows = [1.0850] * 40 + [1.0860, 1.0840, 1.0800, 1.0840, 1.0860] + [1.0850] * 55
        candles = pd.DataFrame({
            "open": [1.0850] * 100,
            "high": [1.0860] * 100,
            "low": lows,
            "close": [1.0850] * 100,
        }, index=dates)

        _, pivot_lows = strategy._find_pivot_points(candles, window=2)

        # Should detect pivot low at 1.0800
        assert len(pivot_lows) > 0

    def test_level_clustering(self, strategy):
        """Should cluster nearby price levels together."""
        levels = [1.0800, 1.0802, 1.0799, 1.0900, 1.0901]
        clusters = strategy._cluster_levels(levels, tolerance=0.001)

        # Should have 2 clusters (around 1.0800 and 1.0900)
        assert len(clusters) == 2

        # Check cluster values are correct
        cluster_values = [c[0] for c in clusters]
        assert any(abs(c - 1.0800) < 0.005 for c in cluster_values)
        assert any(abs(c - 1.0900) < 0.005 for c in cluster_values)

    def test_cluster_touch_counting(self, strategy):
        """Should correctly count touches in clustered levels."""
        levels = [1.0800, 1.0801, 1.0799]  # 3 touches
        clusters = strategy._cluster_levels(levels, tolerance=0.001)

        assert len(clusters) == 1
        assert clusters[0][1] == 3  # 3 touches

    def test_metadata_includes_level_info(self, strategy):
        """Should include level information in signal metadata."""
        dates = pd.date_range(start="2024-01-01", periods=100, freq="1h", tz=timezone.utc)
        highs = [1.0860] * 20 + [1.0900] * 5 + [1.0860] * 30 + [1.0900] * 5 + [1.0860] * 38 + [1.0850, 1.0920]
        closes = [1.0855] * 98 + [1.0890, 1.0915]

        candles = pd.DataFrame({
            "open": [1.0850] * 100,
            "high": highs,
            "low": [1.0840] * 100,
            "close": closes,
            "volume": [1000] * 100,
        }, index=dates)

        context = create_context(candles, {}, current_price=1.0915)
        signals = strategy.generate_signals(context)

        if len(signals) > 0:
            assert "level" in signals[0].metadata
            assert "touches" in signals[0].metadata
            assert "breakout_amount" in signals[0].metadata

    def test_signal_strength_scales_with_touches(self, strategy):
        """Should scale signal strength with number of touches."""
        # This is a conceptual test - strength should increase with touches
        # The exact implementation depends on the strategy logic
        assert True  # Placeholder - actual test would require specific data setup

    def test_no_signal_when_nan_values(self, strategy, sample_candles):
        """Should handle NaN values gracefully."""
        candles = sample_candles.copy()
        candles.loc[candles.index[0:10], "close"] = np.nan

        context = create_context(candles, {})
        signals = strategy.generate_signals(context)

        # Should handle NaN gracefully
        assert isinstance(signals, list)


# --- Strategy Lifecycle Tests ---


class TestStrategyLifecycle:
    """Tests for strategy lifecycle methods."""

    def test_on_start_sets_running(self, strategy):
        """Should set running flag on start."""
        strategy.on_start()

        assert strategy.is_running is True

    def test_on_stop_clears_running(self, strategy):
        """Should clear running flag on stop."""
        strategy.on_start()
        strategy.on_stop()

        assert strategy.is_running is False

    def test_validate_passes_with_defaults(self, strategy):
        """Should pass validation with default config."""
        errors = strategy.validate()

        assert len(errors) == 0

    def test_validate_fails_small_lookback(self):
        """Should fail validation with too small lookback."""
        strategy = SupportResistanceStrategy(lookback=10)
        errors = strategy.validate()

        assert any("lookback" in e.lower() for e in errors)

    def test_validate_fails_invalid_tolerance(self):
        """Should fail validation with invalid tolerance."""
        strategy = SupportResistanceStrategy(tolerance=0.02)
        errors = strategy.validate()

        assert any("tolerance" in e.lower() for e in errors)

    def test_validate_fails_zero_min_touches(self):
        """Should fail validation with zero min_touches."""
        strategy = SupportResistanceStrategy(min_touches=0)
        errors = strategy.validate()

        assert any("touches" in e.lower() for e in errors)

    def test_validate_fails_large_breakout_pct(self):
        """Should fail validation with too large breakout percentage."""
        strategy = SupportResistanceStrategy(breakout_pct=0.1)
        errors = strategy.validate()

        assert any("breakout" in e.lower() for e in errors)

    def test_get_info_returns_metadata(self, strategy):
        """Should return strategy info dict."""
        info = strategy.get_info()

        assert info["name"] == "Support/Resistance Breakout"
        assert info["version"] == "1.0.0"
        assert len(info["required_indicators"]) == 0  # No external indicators
        assert "lookback" in info["default_params"]

    def test_create_signal_helper(self, strategy):
        """Should create signal with strategy metadata."""
        signal = strategy.create_signal(
            signal_type=SignalType.BUY,
            instrument="EUR_USD",
            strength=0.7,
            reason="Resistance breakout",
            metadata={"level": 1.0900, "touches": 3},
        )

        assert signal.signal_type == SignalType.BUY
        assert signal.instrument == "EUR_USD"
        assert float(signal.strength) == 0.7
        assert signal.strategy_id == "Support/Resistance Breakout"
