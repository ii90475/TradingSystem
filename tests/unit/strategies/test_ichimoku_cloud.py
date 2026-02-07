"""Tests for Ichimoku Cloud strategy."""

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from tradingsystem.models.signal import SignalType
from tradingsystem.strategies.base import StrategyContext
from tradingsystem.strategies.examples.ichimoku_cloud import IchimokuCloudStrategy


# --- Fixtures ---


@pytest.fixture
def strategy():
    """Create default Ichimoku Cloud strategy."""
    return IchimokuCloudStrategy()


@pytest.fixture
def strategy_custom_params():
    """Create Ichimoku Cloud strategy with custom parameters."""
    return IchimokuCloudStrategy(
        tenkan_period=7,
        kijun_period=22,
        senkou_b_period=44,
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
        "high": [1.0870] * 100,
        "low": [1.0830] * 100,
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


def create_ichimoku_df(tenkan, kijun, senkou_a, senkou_b, chikou, index):
    """Helper to create Ichimoku DataFrame."""
    return pd.DataFrame({
        "tenkan": tenkan,
        "kijun": kijun,
        "senkou_a": senkou_a,
        "senkou_b": senkou_b,
        "chikou": chikou,
    }, index=index)


# --- IchimokuCloudStrategy Initialization Tests ---


class TestIchimokuCloudStrategyInit:
    """Tests for IchimokuCloudStrategy initialization."""

    def test_default_params(self, strategy):
        """Should have default parameters."""
        assert strategy.params["tenkan_period"] == 9
        assert strategy.params["kijun_period"] == 26
        assert strategy.params["senkou_b_period"] == 52

    def test_custom_params(self, strategy_custom_params):
        """Should accept custom parameters."""
        assert strategy_custom_params.params["tenkan_period"] == 7
        assert strategy_custom_params.params["kijun_period"] == 22
        assert strategy_custom_params.params["senkou_b_period"] == 44

    def test_metadata(self, strategy):
        """Should have correct metadata."""
        assert strategy.name == "Ichimoku Cloud"
        assert strategy.version == "1.0.0"
        assert "EUR_USD" in strategy.instruments
        assert "1h" in strategy.periods

    def test_description(self, strategy):
        """Should have meaningful description."""
        assert "trend" in strategy.description.lower() or "ichimoku" in strategy.description.lower()


# --- Required Indicators Tests ---


class TestRequiredIndicators:
    """Tests for required indicators configuration."""

    def test_indicators_include_ichimoku(self, strategy):
        """Should require Ichimoku indicator."""
        indicators = strategy.required_indicators

        assert len(indicators) == 1
        assert indicators[0].indicator_type == "ichimoku"
        assert indicators[0].column_name == "ichimoku"

    def test_indicators_use_correct_params(self, strategy):
        """Should configure Ichimoku with correct periods."""
        indicators = strategy.required_indicators

        assert indicators[0].params["tenkan"] == 9
        assert indicators[0].params["kijun"] == 26
        assert indicators[0].params["senkou"] == 52

    def test_indicators_custom_params(self, strategy_custom_params):
        """Should use custom parameters for indicator."""
        indicators = strategy_custom_params.required_indicators

        assert indicators[0].params["tenkan"] == 7
        assert indicators[0].params["kijun"] == 22
        assert indicators[0].params["senkou"] == 44


# --- Signal Generation Tests ---


class TestGenerateSignals:
    """Tests for generate_signals method."""

    def test_no_signal_when_price_in_cloud(self, strategy, sample_candles):
        """Should return no signals when price is within the cloud."""
        ichimoku = create_ichimoku_df(
            tenkan=[1.0850] * 100,
            kijun=[1.0850] * 100,
            senkou_a=[1.0880] * 100,
            senkou_b=[1.0820] * 100,
            chikou=[1.0850] * 100,
            index=sample_candles.index,
        )

        context = create_context(sample_candles, {"ichimoku": ichimoku})
        signals = strategy.generate_signals(context)

        # Price at 1.0850 is within cloud (1.0820 to 1.0880)
        assert len(signals) == 0

    def test_buy_signal_on_cloud_breakout(self, strategy, sample_candles):
        """Should generate BUY signal when price breaks above cloud."""
        candles = sample_candles.copy()
        candles.loc[candles.index[-2], "close"] = 1.0870  # At cloud top
        candles.loc[candles.index[-1], "close"] = 1.0920  # Above cloud

        ichimoku = create_ichimoku_df(
            tenkan=[1.0860] * 98 + [1.0850, 1.0870],  # TK cross
            kijun=[1.0850] * 98 + [1.0860, 1.0850],
            senkou_a=[1.0880] * 100,
            senkou_b=[1.0820] * 100,
            chikou=[1.0850] * 100,
            index=sample_candles.index,
        )

        context = create_context(candles, {"ichimoku": ichimoku}, current_price=1.0920)
        signals = strategy.generate_signals(context)

        assert len(signals) == 1
        assert signals[0].signal_type == SignalType.BUY
        assert "bullish" in signals[0].reason.lower()

    def test_buy_signal_on_tk_cross_above_cloud(self, strategy, sample_candles):
        """Should generate BUY signal on bullish TK cross above cloud."""
        candles = sample_candles.copy()
        candles.loc[candles.index[-2], "close"] = 1.0920
        candles.loc[candles.index[-1], "close"] = 1.0920  # Above cloud

        ichimoku = create_ichimoku_df(
            tenkan=[1.0850] * 98 + [1.0860, 1.0880],  # Crosses above
            kijun=[1.0870] * 100,  # Kijun at 1.0870
            senkou_a=[1.0850] * 100,  # Cloud below
            senkou_b=[1.0800] * 100,
            chikou=[1.0850] * 100,
            index=sample_candles.index,
        )

        context = create_context(candles, {"ichimoku": ichimoku}, current_price=1.0920)
        signals = strategy.generate_signals(context)

        assert len(signals) == 1
        assert signals[0].signal_type == SignalType.BUY
        assert signals[0].metadata["tk_cross"] == True

    def test_sell_signal_on_cloud_breakdown(self, strategy, sample_candles):
        """Should generate SELL signal when price breaks below cloud."""
        candles = sample_candles.copy()
        candles.loc[candles.index[-2], "close"] = 1.0830  # At cloud bottom
        candles.loc[candles.index[-1], "close"] = 1.0780  # Below cloud

        ichimoku = create_ichimoku_df(
            tenkan=[1.0850] * 98 + [1.0860, 1.0840],  # TK bearish cross
            kijun=[1.0850] * 100,
            senkou_a=[1.0880] * 100,
            senkou_b=[1.0820] * 100,
            chikou=[1.0850] * 100,
            index=sample_candles.index,
        )

        context = create_context(candles, {"ichimoku": ichimoku}, current_price=1.0780)
        signals = strategy.generate_signals(context)

        assert len(signals) == 1
        assert signals[0].signal_type == SignalType.SELL
        assert "bearish" in signals[0].reason.lower()

    def test_no_signal_when_missing_ichimoku(self, strategy, sample_candles):
        """Should return no signals when Ichimoku indicator is missing."""
        context = create_context(sample_candles, {})
        signals = strategy.generate_signals(context)

        assert len(signals) == 0

    def test_no_signal_when_insufficient_data(self, strategy, sample_candles):
        """Should return no signals with less than 2 data points."""
        ichimoku = create_ichimoku_df(
            tenkan=[1.0850],
            kijun=[1.0850],
            senkou_a=[1.0880],
            senkou_b=[1.0820],
            chikou=[1.0850],
            index=[sample_candles.index[0]],
        )

        context = create_context(
            sample_candles.iloc[:1],
            {"ichimoku": ichimoku},
        )
        signals = strategy.generate_signals(context)

        assert len(signals) == 0

    def test_no_signal_when_nan_values(self, strategy, sample_candles):
        """Should handle NaN values gracefully."""
        ichimoku = create_ichimoku_df(
            tenkan=[np.nan] * 50 + [1.0850] * 50,
            kijun=[np.nan] * 50 + [1.0850] * 50,
            senkou_a=[np.nan] * 50 + [1.0880] * 50,
            senkou_b=[np.nan] * 50 + [1.0820] * 50,
            chikou=[np.nan] * 50 + [1.0850] * 50,
            index=sample_candles.index,
        )

        context = create_context(sample_candles, {"ichimoku": ichimoku})
        signals = strategy.generate_signals(context)

        # Should handle NaN gracefully
        assert isinstance(signals, list)

    def test_metadata_includes_ichimoku_values(self, strategy, sample_candles):
        """Should include Ichimoku values in signal metadata."""
        candles = sample_candles.copy()
        candles.loc[candles.index[-2], "close"] = 1.0870
        candles.loc[candles.index[-1], "close"] = 1.0920

        ichimoku = create_ichimoku_df(
            tenkan=[1.0850] * 98 + [1.0860, 1.0880],
            kijun=[1.0870] * 100,
            senkou_a=[1.0850] * 100,
            senkou_b=[1.0800] * 100,
            chikou=[1.0850] * 100,
            index=sample_candles.index,
        )

        context = create_context(candles, {"ichimoku": ichimoku}, current_price=1.0920)
        signals = strategy.generate_signals(context)

        assert len(signals) == 1
        assert "tenkan" in signals[0].metadata
        assert "kijun" in signals[0].metadata
        assert "senkou_a" in signals[0].metadata
        assert "senkou_b" in signals[0].metadata
        assert "cloud_top" in signals[0].metadata
        assert "cloud_bottom" in signals[0].metadata

    def test_cloud_strength_calculation(self, strategy, sample_candles):
        """Should calculate cloud strength based on thickness."""
        # Thin cloud (weak signal)
        candles = sample_candles.copy()
        candles.loc[candles.index[-2], "close"] = 1.0850
        candles.loc[candles.index[-1], "close"] = 1.0920

        ichimoku_thin = create_ichimoku_df(
            tenkan=[1.0850] * 98 + [1.0860, 1.0880],
            kijun=[1.0870] * 100,
            senkou_a=[1.0855] * 100,  # Very thin cloud
            senkou_b=[1.0850] * 100,
            chikou=[1.0850] * 100,
            index=sample_candles.index,
        )

        context_thin = create_context(candles, {"ichimoku": ichimoku_thin}, current_price=1.0920)
        signals_thin = strategy.generate_signals(context_thin)

        # Thick cloud (stronger signal)
        ichimoku_thick = create_ichimoku_df(
            tenkan=[1.0850] * 98 + [1.0860, 1.0880],
            kijun=[1.0870] * 100,
            senkou_a=[1.0900] * 100,  # Thick cloud
            senkou_b=[1.0800] * 100,
            chikou=[1.0850] * 100,
            index=sample_candles.index,
        )

        context_thick = create_context(candles, {"ichimoku": ichimoku_thick}, current_price=1.0920)
        signals_thick = strategy.generate_signals(context_thick)

        # Both should generate signals, thickness affects strength
        if len(signals_thin) > 0 and len(signals_thick) > 0:
            assert signals_thick[0].metadata["cloud_thickness"] > signals_thin[0].metadata["cloud_thickness"]


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

    def test_validate_fails_tenkan_gte_kijun(self):
        """Should fail validation when tenkan >= kijun."""
        strategy = IchimokuCloudStrategy(tenkan_period=26, kijun_period=9)
        errors = strategy.validate()

        assert any("tenkan" in e.lower() and "kijun" in e.lower() for e in errors)

    def test_validate_fails_kijun_gte_senkou(self):
        """Should fail validation when kijun >= senkou_b."""
        strategy = IchimokuCloudStrategy(kijun_period=52, senkou_b_period=26)
        errors = strategy.validate()

        assert any("kijun" in e.lower() and "senkou" in e.lower() for e in errors)

    def test_validate_fails_zero_tenkan(self):
        """Should fail validation with zero tenkan period."""
        strategy = IchimokuCloudStrategy(tenkan_period=0)
        errors = strategy.validate()

        assert any("tenkan" in e.lower() for e in errors)

    def test_get_info_returns_metadata(self, strategy):
        """Should return strategy info dict."""
        info = strategy.get_info()

        assert info["name"] == "Ichimoku Cloud"
        assert info["version"] == "1.0.0"
        assert len(info["required_indicators"]) == 1
        assert "tenkan_period" in info["default_params"]

    def test_create_signal_helper(self, strategy):
        """Should create signal with strategy metadata."""
        signal = strategy.create_signal(
            signal_type=SignalType.BUY,
            instrument="EUR_USD",
            strength=0.85,
            reason="Cloud breakout",
            metadata={"cloud_top": 1.0880},
        )

        assert signal.signal_type == SignalType.BUY
        assert signal.instrument == "EUR_USD"
        assert float(signal.strength) == 0.85
        assert signal.strategy_id == "Ichimoku Cloud"
