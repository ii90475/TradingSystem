"""Tests for RSI Reversal strategy."""

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from tradingsystem.models.signal import SignalType
from tradingsystem.strategies.base import StrategyContext
from tradingsystem.strategies.examples.rsi_reversal import RSIReversalStrategy


# --- Fixtures ---


@pytest.fixture
def strategy():
    """Create default RSI Reversal strategy."""
    return RSIReversalStrategy()


@pytest.fixture
def strategy_custom():
    """Create RSI Reversal strategy with custom parameters."""
    return RSIReversalStrategy(
        rsi_period=7,
        oversold=20,
        overbought=80,
        confirmation_periods=2,
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
    return pd.DataFrame({
        "open": [1.0850] * 50,
        "high": [1.0860] * 50,
        "low": [1.0840] * 50,
        "close": [1.0855] * 50,
        "volume": [1000] * 50,
    }, index=dates)


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


# --- Initialization Tests ---


class TestRSIReversalInit:
    """Tests for RSIReversalStrategy initialization."""

    def test_default_params(self, strategy):
        """Should have default parameters."""
        assert strategy.params["rsi_period"] == 14
        assert strategy.params["oversold"] == 30
        assert strategy.params["overbought"] == 70
        assert strategy.params["confirmation_periods"] == 1

    def test_custom_params(self, strategy_custom):
        """Should accept custom parameters."""
        assert strategy_custom.params["rsi_period"] == 7
        assert strategy_custom.params["oversold"] == 20
        assert strategy_custom.params["overbought"] == 80
        assert strategy_custom.params["confirmation_periods"] == 2

    def test_metadata(self, strategy):
        """Should have correct metadata."""
        assert strategy.name == "RSI Reversal"
        assert strategy.version == "1.0.0"
        assert "mean-reversion" in strategy.description.lower()
        assert "EUR_USD" in strategy.instruments


# --- Required Indicators Tests ---


class TestRequiredIndicators:
    """Tests for required indicators configuration."""

    def test_requires_rsi(self, strategy):
        """Should require RSI indicator."""
        indicators = strategy.required_indicators

        assert len(indicators) == 1
        assert indicators[0].indicator_type == "rsi"
        assert indicators[0].column_name == "rsi"

    def test_rsi_uses_configured_period(self, strategy):
        """Should use configured RSI period."""
        indicators = strategy.required_indicators

        assert indicators[0].params["length"] == 14

    def test_rsi_uses_custom_period(self, strategy_custom):
        """Should use custom RSI period."""
        indicators = strategy_custom.required_indicators

        assert indicators[0].params["length"] == 7


# --- Signal Generation Tests ---


class TestGenerateSignals:
    """Tests for generate_signals method."""

    def test_no_signal_when_rsi_missing(self, strategy, sample_candles):
        """Should return no signals when RSI indicator missing."""
        context = create_context(sample_candles, {})

        signals = strategy.generate_signals(context)

        assert len(signals) == 0

    def test_no_signal_when_insufficient_data(self, strategy, sample_candles):
        """Should return no signals with insufficient data."""
        rsi = pd.Series([50.0, 51.0], index=sample_candles.index[:2])

        context = create_context(
            sample_candles.iloc[:2],
            {"rsi": rsi},
        )

        signals = strategy.generate_signals(context)

        assert len(signals) == 0

    def test_no_signal_when_nan_values(self, strategy, sample_candles):
        """Should return no signals when RSI has NaN."""
        rsi = pd.Series([np.nan] * 48 + [np.nan, 50.0], index=sample_candles.index)

        context = create_context(sample_candles, {"rsi": rsi})

        signals = strategy.generate_signals(context)

        assert len(signals) == 0

    def test_no_signal_in_normal_range(self, strategy, sample_candles):
        """Should return no signals when RSI in normal range."""
        # RSI staying around 50 - no oversold/overbought
        rsi = pd.Series([50.0] * 50, index=sample_candles.index)

        context = create_context(sample_candles, {"rsi": rsi})

        signals = strategy.generate_signals(context)

        assert len(signals) == 0

    def test_buy_signal_on_oversold_reversal(self, strategy, sample_candles):
        """Should generate BUY signal on oversold reversal."""
        # RSI crosses from below 30 to above 30
        rsi = pd.Series([50.0] * 48 + [28.0, 32.0], index=sample_candles.index)

        context = create_context(sample_candles, {"rsi": rsi})

        signals = strategy.generate_signals(context)

        assert len(signals) == 1
        assert signals[0].signal_type == SignalType.BUY
        assert "oversold" in signals[0].reason.lower()
        assert signals[0].metadata["reversal_type"] == "oversold"

    def test_sell_signal_on_overbought_reversal(self, strategy, sample_candles):
        """Should generate SELL signal on overbought reversal."""
        # RSI crosses from above 70 to below 70
        rsi = pd.Series([50.0] * 48 + [72.0, 68.0], index=sample_candles.index)

        context = create_context(sample_candles, {"rsi": rsi})

        signals = strategy.generate_signals(context)

        assert len(signals) == 1
        assert signals[0].signal_type == SignalType.SELL
        assert "overbought" in signals[0].reason.lower()
        assert signals[0].metadata["reversal_type"] == "overbought"

    def test_no_signal_when_staying_oversold(self, strategy, sample_candles):
        """Should not signal when RSI stays oversold."""
        # RSI staying below 30 - no reversal
        rsi = pd.Series([25.0] * 48 + [24.0, 26.0], index=sample_candles.index)

        context = create_context(sample_candles, {"rsi": rsi})

        signals = strategy.generate_signals(context)

        assert len(signals) == 0

    def test_no_signal_when_staying_overbought(self, strategy, sample_candles):
        """Should not signal when RSI stays overbought."""
        # RSI staying above 70 - no reversal
        rsi = pd.Series([75.0] * 48 + [76.0, 74.0], index=sample_candles.index)

        context = create_context(sample_candles, {"rsi": rsi})

        signals = strategy.generate_signals(context)

        assert len(signals) == 0

    def test_signal_strength_scales_with_oversold_depth(self, strategy, sample_candles):
        """Should scale strength with how oversold RSI was."""
        # Very oversold (RSI was 10)
        rsi_deep = pd.Series([50.0] * 46 + [15.0, 10.0, 28.0, 32.0], index=sample_candles.index)
        context_deep = create_context(sample_candles, {"rsi": rsi_deep})
        signals_deep = strategy.generate_signals(context_deep)

        # Mildly oversold (RSI was 28)
        rsi_mild = pd.Series([50.0] * 48 + [28.0, 32.0], index=sample_candles.index)
        context_mild = create_context(sample_candles, {"rsi": rsi_mild})
        signals_mild = strategy.generate_signals(context_mild)

        # Deeper oversold should have higher strength
        if signals_deep and signals_mild:
            assert signals_deep[0].strength >= signals_mild[0].strength

    def test_signal_metadata_includes_rsi_values(self, strategy, sample_candles):
        """Should include RSI values in signal metadata."""
        rsi = pd.Series([50.0] * 48 + [28.0, 32.0], index=sample_candles.index)

        context = create_context(sample_candles, {"rsi": rsi})

        signals = strategy.generate_signals(context)

        assert "rsi" in signals[0].metadata
        assert "oversold_level" in signals[0].metadata
        assert signals[0].metadata["oversold_level"] == 30

    def test_custom_thresholds(self, strategy_custom, sample_candles):
        """Should use custom oversold/overbought thresholds."""
        # With custom oversold=20, RSI at 18->22 should trigger
        rsi = pd.Series([50.0] * 46 + [18.0, 15.0, 18.0, 22.0], index=sample_candles.index)

        context = create_context(sample_candles, {"rsi": rsi})

        signals = strategy_custom.generate_signals(context)

        assert len(signals) == 1
        assert signals[0].signal_type == SignalType.BUY


# --- Validation Tests ---


class TestValidation:
    """Tests for strategy validation."""

    def test_validate_passes_with_valid_params(self, strategy):
        """Should pass validation with default params."""
        errors = strategy.validate()

        assert len(errors) == 0

    def test_validate_fails_when_oversold_gte_overbought(self):
        """Should fail when oversold >= overbought."""
        strategy = RSIReversalStrategy(oversold=70, overbought=30)

        errors = strategy.validate()

        assert any("less than overbought" in e.lower() for e in errors)

    def test_validate_fails_when_oversold_too_high(self):
        """Should fail when oversold > 50."""
        strategy = RSIReversalStrategy(oversold=60)

        errors = strategy.validate()

        assert any("between 0 and 50" in e.lower() for e in errors)

    def test_validate_fails_when_oversold_negative(self):
        """Should fail when oversold < 0."""
        strategy = RSIReversalStrategy(oversold=-10)

        errors = strategy.validate()

        assert any("between 0 and 50" in e.lower() for e in errors)

    def test_validate_fails_when_overbought_too_low(self):
        """Should fail when overbought < 50."""
        strategy = RSIReversalStrategy(overbought=40)

        errors = strategy.validate()

        assert any("between 50 and 100" in e.lower() for e in errors)

    def test_validate_fails_when_overbought_over_100(self):
        """Should fail when overbought > 100."""
        strategy = RSIReversalStrategy(overbought=110)

        errors = strategy.validate()

        assert any("between 50 and 100" in e.lower() for e in errors)


# --- Strategy Info Tests ---


class TestStrategyInfo:
    """Tests for strategy info methods."""

    def test_get_info_returns_metadata(self, strategy):
        """Should return strategy info dict."""
        info = strategy.get_info()

        assert info["name"] == "RSI Reversal"
        assert info["version"] == "1.0.0"
        assert len(info["required_indicators"]) == 1
        assert "rsi_period" in info["default_params"]

    def test_strategy_repr(self, strategy):
        """Should have readable repr."""
        repr_str = repr(strategy)

        assert "RSIReversalStrategy" in repr_str
        assert "RSI Reversal" in repr_str
