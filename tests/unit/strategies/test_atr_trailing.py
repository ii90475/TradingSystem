"""Tests for ATR Trailing Stop strategy."""

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from tradingsystem.models.signal import SignalType
from tradingsystem.strategies.base import StrategyContext
from tradingsystem.strategies.examples.atr_trailing import ATRTrailingStrategy, PositionState


# --- Fixtures ---


@pytest.fixture
def strategy():
    """Create default ATR Trailing Stop strategy."""
    return ATRTrailingStrategy()


@pytest.fixture
def strategy_custom_params():
    """Create ATR Trailing Stop strategy with custom parameters."""
    return ATRTrailingStrategy(
        ema_fast=5,
        ema_slow=15,
        atr_period=10,
        atr_multiplier=1.5,
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
        "close": [1.0850] * 50,
        "volume": [1000] * 50,
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


# --- ATRTrailingStrategy Initialization Tests ---


class TestATRTrailingStrategyInit:
    """Tests for ATRTrailingStrategy initialization."""

    def test_default_params(self, strategy):
        """Should have default parameters."""
        assert strategy.params["ema_fast"] == 10
        assert strategy.params["ema_slow"] == 20
        assert strategy.params["atr_period"] == 14
        assert strategy.params["atr_multiplier"] == 2.0

    def test_custom_params(self, strategy_custom_params):
        """Should accept custom parameters."""
        assert strategy_custom_params.params["ema_fast"] == 5
        assert strategy_custom_params.params["ema_slow"] == 15
        assert strategy_custom_params.params["atr_period"] == 10
        assert strategy_custom_params.params["atr_multiplier"] == 1.5

    def test_metadata(self, strategy):
        """Should have correct metadata."""
        assert strategy.name == "ATR Trailing Stop"
        assert strategy.version == "1.0.0"
        assert "EUR_USD" in strategy.instruments
        assert "1h" in strategy.periods

    def test_description(self, strategy):
        """Should have meaningful description."""
        assert "trailing" in strategy.description.lower() or "atr" in strategy.description.lower()

    def test_position_state_initialized(self, strategy):
        """Should have empty position state on initialization."""
        assert strategy._position_state == {}


# --- Required Indicators Tests ---


class TestRequiredIndicators:
    """Tests for required indicators configuration."""

    def test_indicators_include_emas_and_atr(self, strategy):
        """Should require EMA and ATR indicators."""
        indicators = strategy.required_indicators

        assert len(indicators) == 3
        types = [ind.indicator_type for ind in indicators]
        assert types.count("ema") == 2
        assert types.count("atr") == 1

    def test_indicators_have_correct_names(self, strategy):
        """Should have correct column names for indicators."""
        indicators = strategy.required_indicators
        column_names = [ind.column_name for ind in indicators]

        assert "ema_fast" in column_names
        assert "ema_slow" in column_names
        assert "atr" in column_names

    def test_indicators_use_correct_params(self, strategy):
        """Should configure indicators with correct periods."""
        indicators = strategy.required_indicators

        fast_ind = next(i for i in indicators if i.column_name == "ema_fast")
        slow_ind = next(i for i in indicators if i.column_name == "ema_slow")
        atr_ind = next(i for i in indicators if i.column_name == "atr")

        assert fast_ind.params["length"] == 10
        assert slow_ind.params["length"] == 20
        assert atr_ind.params["length"] == 14


# --- Signal Generation Tests ---


class TestGenerateSignals:
    """Tests for generate_signals method."""

    def test_buy_signal_on_bullish_crossover(self, strategy, sample_candles):
        """Should generate BUY signal on bullish EMA crossover."""
        ema_fast = pd.Series([1.0840] * 48 + [1.0845, 1.0860], index=sample_candles.index)
        ema_slow = pd.Series([1.0850] * 50, index=sample_candles.index)
        atr = pd.Series([0.0020] * 50, index=sample_candles.index)

        context = create_context(
            sample_candles,
            {"ema_fast": ema_fast, "ema_slow": ema_slow, "atr": atr},
            current_price=1.0855,
        )
        signals = strategy.generate_signals(context)

        assert len(signals) == 1
        assert signals[0].signal_type == SignalType.BUY
        assert "bullish" in signals[0].reason.lower()
        assert signals[0].metadata["signal_category"] == "entry"
        assert signals[0].metadata["direction"] == "long"
        assert "initial_stop" in signals[0].metadata

    def test_sell_signal_on_bearish_crossover(self, strategy, sample_candles):
        """Should generate SELL signal on bearish EMA crossover."""
        ema_fast = pd.Series([1.0860] * 48 + [1.0855, 1.0840], index=sample_candles.index)
        ema_slow = pd.Series([1.0850] * 50, index=sample_candles.index)
        atr = pd.Series([0.0020] * 50, index=sample_candles.index)

        context = create_context(
            sample_candles,
            {"ema_fast": ema_fast, "ema_slow": ema_slow, "atr": atr},
            current_price=1.0845,
        )
        signals = strategy.generate_signals(context)

        assert len(signals) == 1
        assert signals[0].signal_type == SignalType.SELL
        assert "bearish" in signals[0].reason.lower()
        assert signals[0].metadata["signal_category"] == "entry"
        assert signals[0].metadata["direction"] == "short"

    def test_position_state_created_on_entry(self, strategy, sample_candles):
        """Should create position state when entry signal is generated."""
        ema_fast = pd.Series([1.0840] * 48 + [1.0845, 1.0860], index=sample_candles.index)
        ema_slow = pd.Series([1.0850] * 50, index=sample_candles.index)
        atr = pd.Series([0.0020] * 50, index=sample_candles.index)

        context = create_context(
            sample_candles,
            {"ema_fast": ema_fast, "ema_slow": ema_slow, "atr": atr},
            current_price=1.0855,
        )
        strategy.generate_signals(context)

        position = strategy.get_position_state("EUR_USD")
        assert position is not None
        assert position.direction == "long"
        assert position.entry_price == 1.0855

    def test_exit_signal_when_stop_hit(self, strategy, sample_candles):
        """Should generate exit signal when trailing stop is hit."""
        # First, create a long position
        strategy._position_state["EUR_USD"] = PositionState(
            direction="long",
            entry_price=1.0850,
            stop_loss=1.0810,
            highest_price=1.0850,
        )

        ema_fast = pd.Series([1.0850] * 50, index=sample_candles.index)
        ema_slow = pd.Series([1.0850] * 50, index=sample_candles.index)
        atr = pd.Series([0.0020] * 50, index=sample_candles.index)

        # Price drops below stop
        context = create_context(
            sample_candles,
            {"ema_fast": ema_fast, "ema_slow": ema_slow, "atr": atr},
            current_price=1.0800,  # Below stop of 1.0810
        )
        signals = strategy.generate_signals(context)

        assert len(signals) == 1
        assert signals[0].signal_type == SignalType.SELL  # Exit long
        assert signals[0].metadata["signal_category"] == "exit"
        assert signals[0].metadata["exit_type"] == "trailing_stop"

    def test_position_cleared_after_exit(self, strategy, sample_candles):
        """Should clear position state after exit signal."""
        strategy._position_state["EUR_USD"] = PositionState(
            direction="long",
            entry_price=1.0850,
            stop_loss=1.0810,
            highest_price=1.0850,
        )

        ema_fast = pd.Series([1.0850] * 50, index=sample_candles.index)
        ema_slow = pd.Series([1.0850] * 50, index=sample_candles.index)
        atr = pd.Series([0.0020] * 50, index=sample_candles.index)

        context = create_context(
            sample_candles,
            {"ema_fast": ema_fast, "ema_slow": ema_slow, "atr": atr},
            current_price=1.0800,
        )
        strategy.generate_signals(context)

        position = strategy.get_position_state("EUR_USD")
        assert position is None

    def test_trailing_stop_updates_for_long(self, strategy, sample_candles):
        """Should update trailing stop as price moves up for long position."""
        strategy._position_state["EUR_USD"] = PositionState(
            direction="long",
            entry_price=1.0850,
            stop_loss=1.0810,
            highest_price=1.0850,
        )

        ema_fast = pd.Series([1.0850] * 50, index=sample_candles.index)
        ema_slow = pd.Series([1.0850] * 50, index=sample_candles.index)
        atr = pd.Series([0.0020] * 50, index=sample_candles.index)

        # Price moves up - no crossover, no stop hit
        context = create_context(
            sample_candles,
            {"ema_fast": ema_fast, "ema_slow": ema_slow, "atr": atr},
            current_price=1.0900,  # Price moved up
        )
        signals = strategy.generate_signals(context)

        # No signal, but stop should be updated
        position = strategy.get_position_state("EUR_USD")
        assert position is not None
        assert position.highest_price == 1.0900
        # Stop should have moved up (1.0900 - 0.002*2.0 = 1.0860)
        assert position.stop_loss == pytest.approx(1.0860, rel=0.001)

    def test_trailing_stop_updates_for_short(self, strategy, sample_candles):
        """Should update trailing stop as price moves down for short position."""
        strategy._position_state["EUR_USD"] = PositionState(
            direction="short",
            entry_price=1.0850,
            stop_loss=1.0890,
            lowest_price=1.0850,
        )

        ema_fast = pd.Series([1.0850] * 50, index=sample_candles.index)
        ema_slow = pd.Series([1.0850] * 50, index=sample_candles.index)
        atr = pd.Series([0.0020] * 50, index=sample_candles.index)

        # Price moves down - no crossover, no stop hit
        context = create_context(
            sample_candles,
            {"ema_fast": ema_fast, "ema_slow": ema_slow, "atr": atr},
            current_price=1.0800,  # Price moved down
        )
        signals = strategy.generate_signals(context)

        # No signal, but stop should be updated
        position = strategy.get_position_state("EUR_USD")
        assert position is not None
        assert position.lowest_price == 1.0800
        # Stop should have moved down (1.0800 + 0.002*2.0 = 1.0840)
        assert position.stop_loss == pytest.approx(1.0840, rel=0.001)

    def test_no_signal_when_missing_indicators(self, strategy, sample_candles):
        """Should return no signals when indicators are missing."""
        context = create_context(sample_candles, {})
        signals = strategy.generate_signals(context)

        assert len(signals) == 0

    def test_no_signal_when_insufficient_data(self, strategy, sample_candles):
        """Should return no signals with less than 2 data points."""
        ema_fast = pd.Series([1.0850], index=[sample_candles.index[0]])
        ema_slow = pd.Series([1.0850], index=[sample_candles.index[0]])
        atr = pd.Series([0.0020], index=[sample_candles.index[0]])

        context = create_context(
            sample_candles.iloc[:1],
            {"ema_fast": ema_fast, "ema_slow": ema_slow, "atr": atr},
        )
        signals = strategy.generate_signals(context)

        assert len(signals) == 0

    def test_no_signal_when_nan_values(self, strategy, sample_candles):
        """Should handle NaN values gracefully."""
        ema_fast = pd.Series([np.nan] * 48 + [1.0850, 1.0860], index=sample_candles.index)
        ema_slow = pd.Series([1.0850] * 50, index=sample_candles.index)
        atr = pd.Series([np.nan] * 50, index=sample_candles.index)

        context = create_context(
            sample_candles,
            {"ema_fast": ema_fast, "ema_slow": ema_slow, "atr": atr},
        )
        signals = strategy.generate_signals(context)

        # Should handle NaN gracefully
        assert isinstance(signals, list)

    def test_stop_loss_calculation(self, strategy):
        """Should correctly calculate stop loss based on ATR."""
        stop_long = strategy._calculate_stop_loss(1.0850, 0.0020, "long")
        stop_short = strategy._calculate_stop_loss(1.0850, 0.0020, "short")

        # Long: 1.0850 - (0.0020 * 2.0) = 1.0810
        assert stop_long == pytest.approx(1.0810, rel=0.001)
        # Short: 1.0850 + (0.0020 * 2.0) = 1.0890
        assert stop_short == pytest.approx(1.0890, rel=0.001)


# --- Position State Tests ---


class TestPositionState:
    """Tests for position state management."""

    def test_get_position_state(self, strategy):
        """Should return position state for instrument."""
        strategy._position_state["EUR_USD"] = PositionState(
            direction="long",
            entry_price=1.0850,
            stop_loss=1.0810,
        )

        position = strategy.get_position_state("EUR_USD")
        assert position is not None
        assert position.direction == "long"

    def test_get_position_state_none(self, strategy):
        """Should return None for instrument without position."""
        position = strategy.get_position_state("GBP_USD")
        assert position is None

    def test_clear_position(self, strategy):
        """Should clear position for instrument."""
        strategy._position_state["EUR_USD"] = PositionState(
            direction="long",
            entry_price=1.0850,
            stop_loss=1.0810,
        )

        strategy.clear_position("EUR_USD")
        assert strategy.get_position_state("EUR_USD") is None

    def test_clear_nonexistent_position(self, strategy):
        """Should handle clearing nonexistent position gracefully."""
        strategy.clear_position("GBP_USD")  # Should not raise


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

    def test_on_stop_clears_positions(self, strategy):
        """Should clear all position state on stop."""
        strategy._position_state["EUR_USD"] = PositionState(
            direction="long",
            entry_price=1.0850,
            stop_loss=1.0810,
        )
        strategy._position_state["GBP_USD"] = PositionState(
            direction="short",
            entry_price=1.3000,
            stop_loss=1.3050,
        )

        strategy.on_stop()

        assert strategy._position_state == {}

    def test_validate_passes_with_defaults(self, strategy):
        """Should pass validation with default config."""
        errors = strategy.validate()

        assert len(errors) == 0

    def test_validate_fails_fast_gte_slow(self):
        """Should fail validation when fast >= slow."""
        strategy = ATRTrailingStrategy(ema_fast=20, ema_slow=10)
        errors = strategy.validate()

        assert any("fast" in e.lower() and "slow" in e.lower() for e in errors)

    def test_validate_fails_small_atr_period(self):
        """Should fail validation with too small ATR period."""
        strategy = ATRTrailingStrategy(atr_period=2)
        errors = strategy.validate()

        assert any("atr" in e.lower() and "period" in e.lower() for e in errors)

    def test_validate_fails_zero_atr_multiplier(self):
        """Should fail validation with zero ATR multiplier."""
        strategy = ATRTrailingStrategy(atr_multiplier=0)
        errors = strategy.validate()

        assert any("multiplier" in e.lower() and "positive" in e.lower() for e in errors)

    def test_validate_fails_large_atr_multiplier(self):
        """Should fail validation with too large ATR multiplier."""
        strategy = ATRTrailingStrategy(atr_multiplier=15)
        errors = strategy.validate()

        assert any("multiplier" in e.lower() for e in errors)

    def test_get_info_returns_metadata(self, strategy):
        """Should return strategy info dict."""
        info = strategy.get_info()

        assert info["name"] == "ATR Trailing Stop"
        assert info["version"] == "1.0.0"
        assert len(info["required_indicators"]) == 3
        assert "atr_multiplier" in info["default_params"]

    def test_create_signal_helper(self, strategy):
        """Should create signal with strategy metadata."""
        signal = strategy.create_signal(
            signal_type=SignalType.BUY,
            instrument="EUR_USD",
            strength=0.75,
            reason="Bullish crossover",
            metadata={"initial_stop": 1.0810},
        )

        assert signal.signal_type == SignalType.BUY
        assert signal.instrument == "EUR_USD"
        assert float(signal.strength) == 0.75
        assert signal.strategy_id == "ATR Trailing Stop"
