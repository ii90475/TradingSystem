"""Tests for MA Crossover strategy."""

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from tradingsystem.models.signal import SignalType
from tradingsystem.strategies.base import IndicatorConfig, StrategyContext
from tradingsystem.strategies.examples.ma_crossover import MACrossoverStrategy


# --- Fixtures ---


@pytest.fixture
def strategy():
    """Create default MA Crossover strategy."""
    return MACrossoverStrategy()


@pytest.fixture
def strategy_custom_params():
    """Create MA Crossover strategy with custom parameters."""
    return MACrossoverStrategy(
        fast_period=5,
        slow_period=10,
        ma_type="sma",
    )


@pytest.fixture
def sample_candles():
    """Create sample OHLCV data."""
    dates = pd.date_range(
        start="2024-01-01",
        periods=50,
        freq="1h",
        tz=timezone.utc,
    )
    data = {
        "open": [1.0850] * 50,
        "high": [1.0860] * 50,
        "low": [1.0840] * 50,
        "close": [1.0855] * 50,
        "volume": [1000] * 50,
    }
    return pd.DataFrame(data, index=dates)


def create_context(candles, indicators, current_price=1.0855):
    """Helper to create StrategyContext."""
    return StrategyContext(
        instrument="EUR_USD",
        period="1h",
        candles=candles,
        indicators=indicators,
        current_time=candles.index[-1],
        current_price=current_price,
    )


# --- MACrossoverStrategy Initialization Tests ---


class TestMACrossoverStrategyInit:
    """Tests for MACrossoverStrategy initialization."""

    def test_default_params(self, strategy):
        """Should have default parameters."""
        assert strategy.params["fast_period"] == 10
        assert strategy.params["slow_period"] == 20
        assert strategy.params["ma_type"] == "ema"

    def test_custom_params(self, strategy_custom_params):
        """Should accept custom parameters."""
        assert strategy_custom_params.params["fast_period"] == 5
        assert strategy_custom_params.params["slow_period"] == 10
        assert strategy_custom_params.params["ma_type"] == "sma"

    def test_metadata(self, strategy):
        """Should have correct metadata."""
        assert strategy.name == "MA Crossover"
        assert strategy.version == "1.0.0"
        assert "EUR_USD" in strategy.instruments
        assert "1h" in strategy.periods


# --- Required Indicators Tests ---


class TestRequiredIndicators:
    """Tests for required indicators configuration."""

    def test_indicators_use_correct_ma_type(self, strategy):
        """Should configure indicators with specified MA type."""
        indicators = strategy.required_indicators

        assert len(indicators) == 2
        assert all(ind.indicator_type == "ema" for ind in indicators)

    def test_indicators_use_correct_periods(self, strategy):
        """Should configure indicators with correct periods."""
        indicators = strategy.required_indicators

        fast_ind = next(i for i in indicators if i.column_name == "fast_ma")
        slow_ind = next(i for i in indicators if i.column_name == "slow_ma")

        assert fast_ind.params["length"] == 10
        assert slow_ind.params["length"] == 20

    def test_indicators_custom_params(self, strategy_custom_params):
        """Should use custom MA type and periods."""
        indicators = strategy_custom_params.required_indicators

        assert all(ind.indicator_type == "sma" for ind in indicators)

        fast_ind = next(i for i in indicators if i.column_name == "fast_ma")
        slow_ind = next(i for i in indicators if i.column_name == "slow_ma")

        assert fast_ind.params["length"] == 5
        assert slow_ind.params["length"] == 10


# --- Signal Generation Tests ---


class TestGenerateSignals:
    """Tests for generate_signals method."""

    def test_no_signal_when_no_crossover(self, strategy, sample_candles):
        """Should return no signals when no crossover."""
        # Both MAs at same level - no crossover
        fast_ma = pd.Series([1.0855] * 50, index=sample_candles.index)
        slow_ma = pd.Series([1.0855] * 50, index=sample_candles.index)

        context = create_context(
            sample_candles,
            {"fast_ma": fast_ma, "slow_ma": slow_ma},
        )

        signals = strategy.generate_signals(context)

        assert len(signals) == 0

    def test_buy_signal_on_bullish_crossover(self, strategy, sample_candles):
        """Should generate BUY signal on bullish crossover."""
        # Fast MA crosses above slow MA at the END of the series (strategy uses iloc[-1], iloc[-2])
        fast_ma = pd.Series([1.0830] * 48 + [1.0840, 1.0860], index=sample_candles.index)
        slow_ma = pd.Series([1.0850] * 50, index=sample_candles.index)

        context = create_context(
            sample_candles,
            {"fast_ma": fast_ma, "slow_ma": slow_ma},
        )

        signals = strategy.generate_signals(context)

        assert len(signals) == 1
        assert signals[0].signal_type == SignalType.BUY
        assert "Bullish" in signals[0].reason
        assert signals[0].metadata["crossover_type"] == "bullish"

    def test_sell_signal_on_bearish_crossover(self, strategy, sample_candles):
        """Should generate SELL signal on bearish crossover."""
        # Fast MA crosses below slow MA at the END of the series
        fast_ma = pd.Series([1.0870] * 48 + [1.0860, 1.0840], index=sample_candles.index)
        slow_ma = pd.Series([1.0850] * 50, index=sample_candles.index)

        context = create_context(
            sample_candles,
            {"fast_ma": fast_ma, "slow_ma": slow_ma},
        )

        signals = strategy.generate_signals(context)

        assert len(signals) == 1
        assert signals[0].signal_type == SignalType.SELL
        assert "Bearish" in signals[0].reason
        assert signals[0].metadata["crossover_type"] == "bearish"

    def test_no_signal_when_missing_fast_ma(self, strategy, sample_candles):
        """Should return no signals when fast_ma missing."""
        slow_ma = pd.Series([1.0850] * 50, index=sample_candles.index)

        context = create_context(
            sample_candles,
            {"slow_ma": slow_ma},  # No fast_ma
        )

        signals = strategy.generate_signals(context)

        assert len(signals) == 0

    def test_no_signal_when_missing_slow_ma(self, strategy, sample_candles):
        """Should return no signals when slow_ma missing."""
        fast_ma = pd.Series([1.0855] * 50, index=sample_candles.index)

        context = create_context(
            sample_candles,
            {"fast_ma": fast_ma},  # No slow_ma
        )

        signals = strategy.generate_signals(context)

        assert len(signals) == 0

    def test_no_signal_when_insufficient_data(self, strategy, sample_candles):
        """Should return no signals with less than 2 data points."""
        fast_ma = pd.Series([1.0855], index=[sample_candles.index[0]])
        slow_ma = pd.Series([1.0850], index=[sample_candles.index[0]])

        context = create_context(
            sample_candles.iloc[:1],
            {"fast_ma": fast_ma, "slow_ma": slow_ma},
        )

        signals = strategy.generate_signals(context)

        assert len(signals) == 0

    def test_no_signal_when_nan_values(self, strategy, sample_candles):
        """Should return no signals when MA values are NaN."""
        fast_ma = pd.Series([np.nan, np.nan] + [1.0860] * 48, index=sample_candles.index)
        slow_ma = pd.Series([1.0850] * 50, index=sample_candles.index)

        context = create_context(
            sample_candles,
            {"fast_ma": fast_ma, "slow_ma": slow_ma},
        )

        signals = strategy.generate_signals(context)

        assert len(signals) == 0

    def test_signal_strength_scales_with_crossover_magnitude(self, strategy, sample_candles):
        """Should scale signal strength with crossover magnitude."""
        # Large crossover at end of series
        fast_ma_large = pd.Series([1.0850] * 48 + [1.0800, 1.0900], index=sample_candles.index)
        slow_ma = pd.Series([1.0850] * 50, index=sample_candles.index)

        context_large = create_context(
            sample_candles,
            {"fast_ma": fast_ma_large, "slow_ma": slow_ma},
        )

        signals_large = strategy.generate_signals(context_large)

        # Small crossover at end of series
        fast_ma_small = pd.Series([1.0850] * 48 + [1.0849, 1.0851], index=sample_candles.index)

        context_small = create_context(
            sample_candles,
            {"fast_ma": fast_ma_small, "slow_ma": slow_ma},
        )

        signals_small = strategy.generate_signals(context_small)

        # Large crossover should have higher strength
        assert signals_large[0].strength > signals_small[0].strength

    def test_signal_metadata_includes_ma_values(self, strategy, sample_candles):
        """Should include MA values in signal metadata."""
        # Crossover at end of series
        fast_ma = pd.Series([1.0830] * 48 + [1.0840, 1.0860], index=sample_candles.index)
        slow_ma = pd.Series([1.0850] * 50, index=sample_candles.index)

        context = create_context(
            sample_candles,
            {"fast_ma": fast_ma, "slow_ma": slow_ma},
        )

        signals = strategy.generate_signals(context)

        assert "fast_ma" in signals[0].metadata
        assert "slow_ma" in signals[0].metadata
        assert "price" in signals[0].metadata

    def test_signal_reason_includes_parameters(self, strategy, sample_candles):
        """Should include MA parameters in signal reason."""
        # Crossover at end of series
        fast_ma = pd.Series([1.0830] * 48 + [1.0840, 1.0860], index=sample_candles.index)
        slow_ma = pd.Series([1.0850] * 50, index=sample_candles.index)

        context = create_context(
            sample_candles,
            {"fast_ma": fast_ma, "slow_ma": slow_ma},
        )

        signals = strategy.generate_signals(context)

        assert "EMA(10)" in signals[0].reason
        assert "EMA(20)" in signals[0].reason


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

    def test_validate_passes(self, strategy):
        """Should pass validation with valid config."""
        errors = strategy.validate()

        assert len(errors) == 0

    def test_get_info_returns_metadata(self, strategy):
        """Should return strategy info dict."""
        info = strategy.get_info()

        assert info["name"] == "MA Crossover"
        assert info["version"] == "1.0.0"
        assert len(info["required_indicators"]) == 2
        assert "fast_period" in info["default_params"]

    def test_create_signal_helper(self, strategy):
        """Should create signal with strategy metadata."""
        signal = strategy.create_signal(
            signal_type=SignalType.BUY,
            instrument="EUR_USD",
            strength=0.8,
            reason="Test signal",
            metadata={"key": "value"},
        )

        assert signal.signal_type == SignalType.BUY
        assert signal.instrument == "EUR_USD"
        assert float(signal.strength) == 0.8  # Compare as float since model uses Decimal
        assert signal.strategy_id == "MA Crossover"
        assert signal.metadata["key"] == "value"

    def test_signal_strength_clamped(self, strategy):
        """Should clamp signal strength to 0-1 range."""
        signal_high = strategy.create_signal(
            signal_type=SignalType.BUY,
            instrument="EUR_USD",
            strength=1.5,  # Over 1
        )
        signal_low = strategy.create_signal(
            signal_type=SignalType.SELL,
            instrument="EUR_USD",
            strength=-0.5,  # Under 0
        )

        assert float(signal_high.strength) == 1.0
        assert float(signal_low.strength) == 0.0
