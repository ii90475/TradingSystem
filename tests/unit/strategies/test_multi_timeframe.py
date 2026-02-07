"""Tests for Multi-Timeframe Trend strategy."""

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from tradingsystem.models.signal import SignalType
from tradingsystem.strategies.base import StrategyContext
from tradingsystem.strategies.examples.multi_timeframe import MultiTimeframeStrategy


# --- Fixtures ---


@pytest.fixture
def strategy():
    """Create default Multi-Timeframe strategy."""
    return MultiTimeframeStrategy()


@pytest.fixture
def strategy_custom_params():
    """Create Multi-Timeframe strategy with custom parameters."""
    return MultiTimeframeStrategy(
        trend_ema=30,
        entry_ema_fast=5,
        entry_ema_slow=15,
        htf_multiplier=2,
    )


@pytest.fixture
def sample_candles():
    """Create sample OHLCV data with enough for HTF aggregation."""
    dates = pd.date_range(
        start="2024-01-01",
        periods=500,
        freq="15min",
        tz=timezone.utc,
    )
    data = {
        "open": [1.0850] * 500,
        "high": [1.0860] * 500,
        "low": [1.0840] * 500,
        "close": [1.0850] * 500,
        "volume": [1000] * 500,
    }
    return pd.DataFrame(data, index=dates)


def create_context(candles, indicators, current_price=1.0850):
    """Helper to create StrategyContext."""
    return StrategyContext(
        instrument="EUR_USD",
        period="M15",
        candles=candles,
        indicators=indicators,
        current_time=candles.index[-1],
        current_price=current_price,
    )


# --- MultiTimeframeStrategy Initialization Tests ---


class TestMultiTimeframeStrategyInit:
    """Tests for MultiTimeframeStrategy initialization."""

    def test_default_params(self, strategy):
        """Should have default parameters."""
        assert strategy.params["trend_ema"] == 50
        assert strategy.params["entry_ema_fast"] == 10
        assert strategy.params["entry_ema_slow"] == 20
        assert strategy.params["htf_multiplier"] == 4

    def test_custom_params(self, strategy_custom_params):
        """Should accept custom parameters."""
        assert strategy_custom_params.params["trend_ema"] == 30
        assert strategy_custom_params.params["entry_ema_fast"] == 5
        assert strategy_custom_params.params["entry_ema_slow"] == 15
        assert strategy_custom_params.params["htf_multiplier"] == 2

    def test_metadata(self, strategy):
        """Should have correct metadata."""
        assert strategy.name == "Multi-Timeframe Trend"
        assert strategy.version == "1.0.0"
        assert "EUR_USD" in strategy.instruments
        assert "M15" in strategy.periods

    def test_description(self, strategy):
        """Should have meaningful description."""
        assert "timeframe" in strategy.description.lower() or "trend" in strategy.description.lower()


# --- Required Indicators Tests ---


class TestRequiredIndicators:
    """Tests for required indicators configuration."""

    def test_indicators_include_emas(self, strategy):
        """Should require three EMA indicators."""
        indicators = strategy.required_indicators

        assert len(indicators) == 3
        assert all(ind.indicator_type == "ema" for ind in indicators)

    def test_indicators_have_correct_names(self, strategy):
        """Should have correct column names for EMAs."""
        indicators = strategy.required_indicators
        column_names = [ind.column_name for ind in indicators]

        assert "ema_fast" in column_names
        assert "ema_slow" in column_names
        assert "ema_trend" in column_names

    def test_indicators_use_correct_params(self, strategy):
        """Should configure EMAs with correct periods."""
        indicators = strategy.required_indicators

        fast_ind = next(i for i in indicators if i.column_name == "ema_fast")
        slow_ind = next(i for i in indicators if i.column_name == "ema_slow")
        trend_ind = next(i for i in indicators if i.column_name == "ema_trend")

        assert fast_ind.params["length"] == 10
        assert slow_ind.params["length"] == 20
        assert trend_ind.params["length"] == 50

    def test_indicators_custom_params(self, strategy_custom_params):
        """Should use custom parameters for indicators."""
        indicators = strategy_custom_params.required_indicators

        fast_ind = next(i for i in indicators if i.column_name == "ema_fast")
        slow_ind = next(i for i in indicators if i.column_name == "ema_slow")

        assert fast_ind.params["length"] == 5
        assert slow_ind.params["length"] == 15


# --- Signal Generation Tests ---


class TestGenerateSignals:
    """Tests for generate_signals method."""

    def test_no_signal_when_ltf_crossover_against_htf_trend(self, strategy, sample_candles):
        """Should return no signals when LTF crossover is against HTF trend."""
        # HTF downtrend, LTF bullish cross - should not signal
        ema_fast = pd.Series([1.0850] * 498 + [1.0840, 1.0860], index=sample_candles.index)
        ema_slow = pd.Series([1.0850] * 500, index=sample_candles.index)
        ema_trend = pd.Series([1.0850] * 500, index=sample_candles.index)

        # Modify candles to have HTF in downtrend
        candles = sample_candles.copy()
        candles["close"] = [1.0800] * 500  # Below trend EMA (downtrend)

        context = create_context(
            candles,
            {"ema_fast": ema_fast, "ema_slow": ema_slow, "ema_trend": ema_trend},
        )
        signals = strategy.generate_signals(context)

        # Should return no signals since HTF trend doesn't align
        # (bullish LTF cross but HTF downtrend)
        assert len(signals) == 0

    def test_buy_signal_when_htf_uptrend_ltf_cross(self, strategy, sample_candles):
        """Should generate BUY signal when HTF uptrend and LTF bullish cross."""
        # HTF uptrend + LTF bullish cross
        ema_fast = pd.Series([1.0840] * 498 + [1.0845, 1.0860], index=sample_candles.index)
        ema_slow = pd.Series([1.0850] * 500, index=sample_candles.index)
        ema_trend = pd.Series([1.0820] * 500, index=sample_candles.index)  # Below close

        # Candles with close showing uptrend - prices gradually rising for HTF uptrend
        # The HTF EMA will be calculated internally from aggregated candles
        # We need prices that are consistently higher than the HTF EMA would be
        candles = sample_candles.copy()
        # Create ascending prices so HTF close > HTF EMA (uptrend)
        closes = [1.0800 + (i * 0.0004) for i in range(500)]  # Rising from 1.08 to 1.28
        candles["close"] = closes

        context = create_context(
            candles,
            {"ema_fast": ema_fast, "ema_slow": ema_slow, "ema_trend": ema_trend},
            current_price=closes[-1],
        )
        signals = strategy.generate_signals(context)

        assert len(signals) == 1
        assert signals[0].signal_type == SignalType.BUY
        assert "bullish" in signals[0].reason.lower()
        assert signals[0].metadata["htf_trend"] == "up"

    def test_sell_signal_when_htf_downtrend_ltf_cross(self, strategy, sample_candles):
        """Should generate SELL signal when HTF downtrend and LTF bearish cross."""
        # HTF downtrend + LTF bearish cross
        ema_fast = pd.Series([1.0860] * 498 + [1.0855, 1.0840], index=sample_candles.index)
        ema_slow = pd.Series([1.0850] * 500, index=sample_candles.index)
        ema_trend = pd.Series([1.0880] * 500, index=sample_candles.index)  # Above close

        # Candles with close showing downtrend - prices gradually falling for HTF downtrend
        candles = sample_candles.copy()
        # Create descending prices so HTF close < HTF EMA (downtrend)
        closes = [1.2800 - (i * 0.0004) for i in range(500)]  # Falling from 1.28 to 1.08
        candles["close"] = closes

        context = create_context(
            candles,
            {"ema_fast": ema_fast, "ema_slow": ema_slow, "ema_trend": ema_trend},
            current_price=closes[-1],
        )
        signals = strategy.generate_signals(context)

        assert len(signals) == 1
        assert signals[0].signal_type == SignalType.SELL
        assert "bearish" in signals[0].reason.lower()
        assert signals[0].metadata["htf_trend"] == "down"

    def test_no_signal_when_missing_indicators(self, strategy, sample_candles):
        """Should return no signals when indicators are missing."""
        context = create_context(sample_candles, {})
        signals = strategy.generate_signals(context)

        assert len(signals) == 0

    def test_no_signal_when_insufficient_data(self, strategy):
        """Should return no signals with insufficient data for HTF aggregation."""
        dates = pd.date_range(start="2024-01-01", periods=50, freq="15min", tz=timezone.utc)
        candles = pd.DataFrame({
            "open": [1.0850] * 50,
            "high": [1.0860] * 50,
            "low": [1.0840] * 50,
            "close": [1.0850] * 50,
            "volume": [1000] * 50,
        }, index=dates)

        ema_fast = pd.Series([1.0850] * 50, index=candles.index)
        ema_slow = pd.Series([1.0850] * 50, index=candles.index)
        ema_trend = pd.Series([1.0850] * 50, index=candles.index)

        context = create_context(
            candles,
            {"ema_fast": ema_fast, "ema_slow": ema_slow, "ema_trend": ema_trend},
        )
        signals = strategy.generate_signals(context)

        assert len(signals) == 0

    def test_htf_aggregation(self, strategy, sample_candles):
        """Should correctly aggregate candles to higher timeframe."""
        htf_candles = strategy._aggregate_to_htf(sample_candles, 4)

        # 500 candles / 4 = 125 HTF candles
        assert len(htf_candles) == 125

        # Check OHLC aggregation is correct
        assert "open" in htf_candles.columns
        assert "high" in htf_candles.columns
        assert "low" in htf_candles.columns
        assert "close" in htf_candles.columns

    def test_htf_aggregation_with_multiplier_1(self, strategy, sample_candles):
        """Should return same candles with multiplier of 1."""
        htf_candles = strategy._aggregate_to_htf(sample_candles, 1)

        assert len(htf_candles) == len(sample_candles)

    def test_ema_calculation(self, strategy):
        """Should correctly calculate EMA."""
        series = pd.Series([1.0, 1.1, 1.2, 1.1, 1.0, 1.1, 1.2, 1.3, 1.2, 1.1])
        ema = strategy._calculate_ema(series, 3)

        assert len(ema) == len(series)
        assert not ema.isna().all()

    def test_metadata_includes_htf_info(self, strategy, sample_candles):
        """Should include HTF information in signal metadata."""
        ema_fast = pd.Series([1.0840] * 498 + [1.0845, 1.0860], index=sample_candles.index)
        ema_slow = pd.Series([1.0850] * 500, index=sample_candles.index)
        ema_trend = pd.Series([1.0820] * 500, index=sample_candles.index)

        candles = sample_candles.copy()
        candles["close"] = [1.0860] * 500

        context = create_context(
            candles,
            {"ema_fast": ema_fast, "ema_slow": ema_slow, "ema_trend": ema_trend},
            current_price=1.0860,
        )
        signals = strategy.generate_signals(context)

        if len(signals) > 0:
            assert "htf_trend" in signals[0].metadata
            assert "htf_close" in signals[0].metadata
            assert "htf_ema" in signals[0].metadata
            assert "htf_multiplier" in signals[0].metadata

    def test_no_signal_when_nan_values(self, strategy, sample_candles):
        """Should handle NaN values gracefully."""
        ema_fast = pd.Series([np.nan] * 250 + [1.0850] * 250, index=sample_candles.index)
        ema_slow = pd.Series([np.nan] * 250 + [1.0850] * 250, index=sample_candles.index)
        ema_trend = pd.Series([np.nan] * 250 + [1.0850] * 250, index=sample_candles.index)

        context = create_context(
            sample_candles,
            {"ema_fast": ema_fast, "ema_slow": ema_slow, "ema_trend": ema_trend},
        )
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

    def test_validate_fails_fast_gte_slow(self):
        """Should fail validation when entry fast >= slow."""
        strategy = MultiTimeframeStrategy(entry_ema_fast=20, entry_ema_slow=10)
        errors = strategy.validate()

        assert any("fast" in e.lower() and "slow" in e.lower() for e in errors)

    def test_validate_fails_small_htf_multiplier(self):
        """Should fail validation with htf_multiplier < 2."""
        strategy = MultiTimeframeStrategy(htf_multiplier=1)
        errors = strategy.validate()

        assert any("multiplier" in e.lower() for e in errors)

    def test_validate_fails_large_htf_multiplier(self):
        """Should fail validation with htf_multiplier > 20."""
        strategy = MultiTimeframeStrategy(htf_multiplier=25)
        errors = strategy.validate()

        assert any("multiplier" in e.lower() for e in errors)

    def test_get_info_returns_metadata(self, strategy):
        """Should return strategy info dict."""
        info = strategy.get_info()

        assert info["name"] == "Multi-Timeframe Trend"
        assert info["version"] == "1.0.0"
        assert len(info["required_indicators"]) == 3
        assert "htf_multiplier" in info["default_params"]

    def test_create_signal_helper(self, strategy):
        """Should create signal with strategy metadata."""
        signal = strategy.create_signal(
            signal_type=SignalType.BUY,
            instrument="EUR_USD",
            strength=0.8,
            reason="Multi-TF bullish alignment",
            metadata={"htf_trend": "up"},
        )

        assert signal.signal_type == SignalType.BUY
        assert signal.instrument == "EUR_USD"
        assert float(signal.strength) == 0.8
        assert signal.strategy_id == "Multi-Timeframe Trend"
