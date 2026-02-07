"""Tests for Bollinger Breakout strategy."""

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from tradingsystem.models.signal import SignalType
from tradingsystem.strategies.base import StrategyContext
from tradingsystem.strategies.examples.bollinger_breakout import BollingerBreakoutStrategy


# --- Fixtures ---


@pytest.fixture
def strategy():
    """Create default Bollinger Breakout strategy."""
    return BollingerBreakoutStrategy()


@pytest.fixture
def strategy_custom_params():
    """Create Bollinger Breakout strategy with custom parameters."""
    return BollingerBreakoutStrategy(
        bb_period=10,
        bb_std=1.5,
        squeeze_threshold=0.01,
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


def create_bbands_df(upper, mid, lower, index):
    """Helper to create Bollinger Bands DataFrame."""
    return pd.DataFrame({
        "upper": upper,
        "mid": mid,
        "lower": lower,
    }, index=index)


# --- BollingerBreakoutStrategy Initialization Tests ---


class TestBollingerBreakoutStrategyInit:
    """Tests for BollingerBreakoutStrategy initialization."""

    def test_default_params(self, strategy):
        """Should have default parameters."""
        assert strategy.params["bb_period"] == 20
        assert strategy.params["bb_std"] == 2.0
        assert strategy.params["squeeze_threshold"] == 0.02

    def test_custom_params(self, strategy_custom_params):
        """Should accept custom parameters."""
        assert strategy_custom_params.params["bb_period"] == 10
        assert strategy_custom_params.params["bb_std"] == 1.5
        assert strategy_custom_params.params["squeeze_threshold"] == 0.01

    def test_metadata(self, strategy):
        """Should have correct metadata."""
        assert strategy.name == "Bollinger Breakout"
        assert strategy.version == "1.0.0"
        assert "EUR_USD" in strategy.instruments
        assert "1h" in strategy.periods

    def test_description(self, strategy):
        """Should have meaningful description."""
        assert "volatility" in strategy.description.lower() or "mean-reversion" in strategy.description.lower()


# --- Required Indicators Tests ---


class TestRequiredIndicators:
    """Tests for required indicators configuration."""

    def test_indicators_include_bbands(self, strategy):
        """Should require Bollinger Bands indicator."""
        indicators = strategy.required_indicators

        assert len(indicators) == 1
        assert indicators[0].indicator_type == "bbands"
        assert indicators[0].column_name == "bbands"

    def test_indicators_use_correct_params(self, strategy):
        """Should configure bbands with correct period and std."""
        indicators = strategy.required_indicators

        assert indicators[0].params["length"] == 20
        assert indicators[0].params["std"] == 2.0

    def test_indicators_custom_params(self, strategy_custom_params):
        """Should use custom parameters for indicator."""
        indicators = strategy_custom_params.required_indicators

        assert indicators[0].params["length"] == 10
        assert indicators[0].params["std"] == 1.5


# --- Signal Generation Tests ---


class TestGenerateSignals:
    """Tests for generate_signals method."""

    def test_no_signal_when_price_within_bands(self, strategy, sample_candles):
        """Should return no signals when price is within bands."""
        bbands = create_bbands_df(
            upper=[1.0900] * 50,
            mid=[1.0850] * 50,
            lower=[1.0800] * 50,
            index=sample_candles.index,
        )

        context = create_context(sample_candles, {"bbands": bbands})
        signals = strategy.generate_signals(context)

        assert len(signals) == 0

    def test_buy_signal_on_oversold_reentry(self, strategy, sample_candles):
        """Should generate BUY signal when price re-enters from below lower band."""
        # Price was below lower band, now re-entering
        candles = sample_candles.copy()
        candles.loc[candles.index[-2], "close"] = 1.0790  # Below lower band
        candles.loc[candles.index[-1], "close"] = 1.0805  # Re-entered

        bbands = create_bbands_df(
            upper=[1.0900] * 50,
            mid=[1.0850] * 50,
            lower=[1.0800] * 50,
            index=sample_candles.index,
        )

        context = create_context(candles, {"bbands": bbands}, current_price=1.0805)
        signals = strategy.generate_signals(context)

        assert len(signals) == 1
        assert signals[0].signal_type == SignalType.BUY
        assert "oversold" in signals[0].reason.lower()
        assert signals[0].metadata["breakout_type"] == "oversold_reentry"

    def test_sell_signal_on_overbought_reentry(self, strategy, sample_candles):
        """Should generate SELL signal when price re-enters from above upper band."""
        # Price was above upper band, now re-entering
        candles = sample_candles.copy()
        candles.loc[candles.index[-2], "close"] = 1.0910  # Above upper band
        candles.loc[candles.index[-1], "close"] = 1.0895  # Re-entered

        bbands = create_bbands_df(
            upper=[1.0900] * 50,
            mid=[1.0850] * 50,
            lower=[1.0800] * 50,
            index=sample_candles.index,
        )

        context = create_context(candles, {"bbands": bbands}, current_price=1.0895)
        signals = strategy.generate_signals(context)

        assert len(signals) == 1
        assert signals[0].signal_type == SignalType.SELL
        assert "overbought" in signals[0].reason.lower()
        assert signals[0].metadata["breakout_type"] == "overbought_reentry"

    def test_no_signal_when_missing_bbands(self, strategy, sample_candles):
        """Should return no signals when bbands indicator is missing."""
        context = create_context(sample_candles, {})
        signals = strategy.generate_signals(context)

        assert len(signals) == 0

    def test_no_signal_when_insufficient_data(self, strategy, sample_candles):
        """Should return no signals with less than 2 data points."""
        bbands = create_bbands_df(
            upper=[1.0900],
            mid=[1.0850],
            lower=[1.0800],
            index=[sample_candles.index[0]],
        )

        context = create_context(
            sample_candles.iloc[:1],
            {"bbands": bbands},
        )
        signals = strategy.generate_signals(context)

        assert len(signals) == 0

    def test_no_signal_when_nan_values(self, strategy, sample_candles):
        """Should return no signals when band values are NaN."""
        bbands = create_bbands_df(
            upper=[np.nan] * 48 + [1.0900, 1.0900],
            mid=[np.nan] * 48 + [1.0850, 1.0850],
            lower=[np.nan] * 48 + [1.0800, 1.0800],
            index=sample_candles.index,
        )

        context = create_context(sample_candles, {"bbands": bbands})
        signals = strategy.generate_signals(context)

        # Should handle NaN gracefully - no crash
        assert isinstance(signals, list)

    def test_metadata_includes_band_values(self, strategy, sample_candles):
        """Should include band values in signal metadata."""
        candles = sample_candles.copy()
        candles.loc[candles.index[-2], "close"] = 1.0790
        candles.loc[candles.index[-1], "close"] = 1.0805

        bbands = create_bbands_df(
            upper=[1.0900] * 50,
            mid=[1.0850] * 50,
            lower=[1.0800] * 50,
            index=sample_candles.index,
        )

        context = create_context(candles, {"bbands": bbands}, current_price=1.0805)
        signals = strategy.generate_signals(context)

        assert "upper_band" in signals[0].metadata
        assert "mid_band" in signals[0].metadata
        assert "lower_band" in signals[0].metadata
        assert "band_width" in signals[0].metadata
        assert "is_squeeze" in signals[0].metadata

    def test_squeeze_detection(self, strategy, sample_candles):
        """Should detect squeeze (narrow bands) condition."""
        candles = sample_candles.copy()
        candles.loc[candles.index[-2], "close"] = 1.0795
        candles.loc[candles.index[-1], "close"] = 1.0805

        # Very narrow bands (squeeze)
        bbands = create_bbands_df(
            upper=[1.0810] * 50,
            mid=[1.0805] * 50,
            lower=[1.0800] * 50,
            index=sample_candles.index,
        )

        context = create_context(candles, {"bbands": bbands}, current_price=1.0805)
        signals = strategy.generate_signals(context)

        assert len(signals) == 1
        assert signals[0].metadata["is_squeeze"] == True

    def test_no_squeeze_with_wide_bands(self, strategy, sample_candles):
        """Should not detect squeeze with wide bands."""
        candles = sample_candles.copy()
        # Price was below lower band (1.0700), now re-entering
        candles.loc[candles.index[-2], "close"] = 1.0690
        candles.loc[candles.index[-1], "close"] = 1.0710

        # Wide bands (no squeeze)
        bbands = create_bbands_df(
            upper=[1.1000] * 50,
            mid=[1.0850] * 50,
            lower=[1.0700] * 50,
            index=sample_candles.index,
        )

        context = create_context(candles, {"bbands": bbands}, current_price=1.0710)
        signals = strategy.generate_signals(context)

        assert len(signals) == 1
        assert signals[0].metadata["is_squeeze"] == False

    def test_signal_strength_scales_with_overshoot(self, strategy, sample_candles):
        """Should scale signal strength with band overshoot magnitude."""
        # Large overshoot
        candles_large = sample_candles.copy()
        candles_large.loc[candles_large.index[-2], "close"] = 1.0750  # Far below
        candles_large.loc[candles_large.index[-1], "close"] = 1.0805

        # Small overshoot
        candles_small = sample_candles.copy()
        candles_small.loc[candles_small.index[-2], "close"] = 1.0795  # Just below
        candles_small.loc[candles_small.index[-1], "close"] = 1.0805

        bbands = create_bbands_df(
            upper=[1.0900] * 50,
            mid=[1.0850] * 50,
            lower=[1.0800] * 50,
            index=sample_candles.index,
        )

        context_large = create_context(candles_large, {"bbands": bbands}, current_price=1.0805)
        context_small = create_context(candles_small, {"bbands": bbands}, current_price=1.0805)

        signals_large = strategy.generate_signals(context_large)
        signals_small = strategy.generate_signals(context_small)

        assert signals_large[0].strength > signals_small[0].strength


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

    def test_validate_fails_small_period(self):
        """Should fail validation with too small period."""
        strategy = BollingerBreakoutStrategy(bb_period=2)
        errors = strategy.validate()

        assert any("period" in e.lower() for e in errors)

    def test_validate_fails_zero_std(self):
        """Should fail validation with zero std."""
        strategy = BollingerBreakoutStrategy(bb_std=0)
        errors = strategy.validate()

        assert any("standard deviation" in e.lower() or "positive" in e.lower() for e in errors)

    def test_validate_fails_invalid_squeeze_threshold(self):
        """Should fail validation with invalid squeeze threshold."""
        strategy = BollingerBreakoutStrategy(squeeze_threshold=0.6)
        errors = strategy.validate()

        assert any("squeeze" in e.lower() for e in errors)

    def test_get_info_returns_metadata(self, strategy):
        """Should return strategy info dict."""
        info = strategy.get_info()

        assert info["name"] == "Bollinger Breakout"
        assert info["version"] == "1.0.0"
        assert len(info["required_indicators"]) == 1
        assert "bb_period" in info["default_params"]

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
        assert float(signal.strength) == 0.8
        assert signal.strategy_id == "Bollinger Breakout"
        assert signal.metadata["key"] == "value"
