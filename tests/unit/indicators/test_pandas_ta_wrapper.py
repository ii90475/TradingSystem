"""Tests for pandas-ta wrapper functions."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from tradingsystem.indicators import pandas_ta_wrapper
from tradingsystem.indicators.pandas_ta_wrapper import (
    INDICATOR_CATEGORIES,
    atr,
    bbands,
    calculate_indicator_ta_method,
    calculate_pandas_ta_indicator,
    ema,
    ensure_initialized,
    macd,
    register_pandas_ta_indicators,
    rsi,
    sma,
    stoch,
)


# --- Fixtures ---


@pytest.fixture
def sample_ohlcv():
    """Create sample OHLCV DataFrame."""
    dates = pd.date_range(start="2024-01-01", periods=50, freq="1h", tz=timezone.utc)
    return pd.DataFrame({
        "open": [1.0850 + i * 0.0001 for i in range(50)],
        "high": [1.0860 + i * 0.0001 for i in range(50)],
        "low": [1.0840 + i * 0.0001 for i in range(50)],
        "close": [1.0855 + i * 0.0001 for i in range(50)],
        "volume": [1000 + i * 10 for i in range(50)],
    }, index=dates)


# --- INDICATOR_CATEGORIES Tests ---


class TestIndicatorCategories:
    """Tests for indicator category definitions."""

    def test_trend_indicators_defined(self):
        """Should have trend indicators."""
        assert "trend" in INDICATOR_CATEGORIES
        assert "sma" in INDICATOR_CATEGORIES["trend"]
        assert "ema" in INDICATOR_CATEGORIES["trend"]
        assert "adx" in INDICATOR_CATEGORIES["trend"]

    def test_momentum_indicators_defined(self):
        """Should have momentum indicators."""
        assert "momentum" in INDICATOR_CATEGORIES
        assert "rsi" in INDICATOR_CATEGORIES["momentum"]
        assert "macd" in INDICATOR_CATEGORIES["momentum"]
        assert "stoch" in INDICATOR_CATEGORIES["momentum"]

    def test_volatility_indicators_defined(self):
        """Should have volatility indicators."""
        assert "volatility" in INDICATOR_CATEGORIES
        assert "atr" in INDICATOR_CATEGORIES["volatility"]
        assert "bbands" in INDICATOR_CATEGORIES["volatility"]

    def test_volume_indicators_defined(self):
        """Should have volume indicators."""
        assert "volume" in INDICATOR_CATEGORIES
        assert "obv" in INDICATOR_CATEGORIES["volume"]
        assert "mfi" in INDICATOR_CATEGORIES["volume"]


# --- register_pandas_ta_indicators Tests ---


class TestRegisterPandasTaIndicators:
    """Tests for register_pandas_ta_indicators function."""

    def test_registers_indicators(self):
        """Should register multiple indicators."""
        with patch("tradingsystem.indicators.pandas_ta_wrapper.IndicatorRegistry") as mock_registry:
            count = register_pandas_ta_indicators()

            assert count > 0
            assert mock_registry.register_pandas_ta.called

    def test_skips_private_methods(self):
        """Should skip methods starting with underscore."""
        with patch("tradingsystem.indicators.pandas_ta_wrapper.IndicatorRegistry") as mock_registry:
            register_pandas_ta_indicators()

            # Check that no private methods were registered
            for call in mock_registry.register_pandas_ta.call_args_list:
                name = call[1]["name"]
                assert not name.startswith("_")


# --- calculate_pandas_ta_indicator Tests ---


class TestCalculatePandasTaIndicator:
    """Tests for calculate_pandas_ta_indicator function."""

    def test_raises_for_unknown_indicator(self, sample_ohlcv):
        """Should raise ValueError for unknown indicator."""
        with patch("tradingsystem.indicators.pandas_ta_wrapper.IndicatorRegistry") as mock_registry:
            mock_registry.get_pandas_ta.return_value = None

            with pytest.raises(ValueError, match="Unknown pandas-ta indicator"):
                calculate_pandas_ta_indicator(sample_ohlcv, "nonexistent_indicator")

    def test_returns_none_for_missing_columns(self):
        """Should return None for missing OHLC columns (error is logged)."""
        df = pd.DataFrame({"close": [1.0, 2.0, 3.0]})  # Missing open, high, low

        mock_func = MagicMock()
        with patch("tradingsystem.indicators.pandas_ta_wrapper.IndicatorRegistry") as mock_registry:
            mock_registry.get_pandas_ta.return_value = {"func": mock_func}

            # The function catches the error and returns None
            result = calculate_pandas_ta_indicator(df, "sma")

            assert result is None

    def test_calls_indicator_function(self, sample_ohlcv):
        """Should call the indicator function with correct args."""
        mock_func = MagicMock(return_value=pd.Series([1.0] * 50))

        with patch("tradingsystem.indicators.pandas_ta_wrapper.IndicatorRegistry") as mock_registry:
            mock_registry.get_pandas_ta.return_value = {"func": mock_func}

            result = calculate_pandas_ta_indicator(sample_ohlcv, "sma", length=20)

            mock_func.assert_called_once()
            assert "length" in mock_func.call_args[1]

    def test_handles_type_error_with_fallback(self, sample_ohlcv):
        """Should try simpler call on TypeError."""
        mock_func = MagicMock()
        mock_func.side_effect = [TypeError("Wrong args"), pd.Series([1.0] * 50)]

        with patch("tradingsystem.indicators.pandas_ta_wrapper.IndicatorRegistry") as mock_registry:
            mock_registry.get_pandas_ta.return_value = {"func": mock_func}

            result = calculate_pandas_ta_indicator(sample_ohlcv, "sma")

            # Should have been called twice - first with full args, then with just close
            assert mock_func.call_count == 2

    def test_returns_none_on_failure(self, sample_ohlcv):
        """Should return None on calculation failure."""
        mock_func = MagicMock(side_effect=Exception("Calculation failed"))

        with patch("tradingsystem.indicators.pandas_ta_wrapper.IndicatorRegistry") as mock_registry:
            mock_registry.get_pandas_ta.return_value = {"func": mock_func}

            result = calculate_pandas_ta_indicator(sample_ohlcv, "sma")

            assert result is None


# --- calculate_indicator_ta_method Tests ---


class TestCalculateIndicatorTaMethod:
    """Tests for calculate_indicator_ta_method function."""

    def test_raises_for_unknown_indicator(self, sample_ohlcv):
        """Should raise ValueError for unknown indicator."""
        with pytest.raises(ValueError, match="Unknown indicator"):
            calculate_indicator_ta_method(sample_ohlcv, "nonexistent_method")

    def test_calls_ta_accessor_method(self, sample_ohlcv):
        """Should use pandas-ta DataFrame accessor."""
        # SMA should work
        result = calculate_indicator_ta_method(sample_ohlcv, "sma", length=10)

        # Result should have SMA column or be a Series
        assert result is not None


# --- Shortcut Function Tests ---


class TestShortcutFunctions:
    """Tests for convenience shortcut functions."""

    def test_sma_calculates(self, sample_ohlcv):
        """SMA shortcut should calculate moving average."""
        result = sma(sample_ohlcv, length=10)

        assert result is not None
        assert len(result) == len(sample_ohlcv)
        # First 9 values should be NaN (not enough data for 10-period SMA)
        assert pd.isna(result.iloc[0])
        assert pd.notna(result.iloc[-1])

    def test_ema_calculates(self, sample_ohlcv):
        """EMA shortcut should calculate exponential moving average."""
        result = ema(sample_ohlcv, length=10)

        assert result is not None
        assert len(result) == len(sample_ohlcv)

    def test_rsi_calculates(self):
        """RSI shortcut should calculate relative strength index."""
        # Create data with price fluctuations for realistic RSI
        dates = pd.date_range(start="2024-01-01", periods=50, freq="1h", tz=timezone.utc)
        import math
        # Oscillating prices to get meaningful RSI (not all 100)
        close_prices = [1.0850 + 0.001 * math.sin(i / 3) for i in range(50)]
        df = pd.DataFrame({
            "open": [p - 0.0005 for p in close_prices],
            "high": [p + 0.001 for p in close_prices],
            "low": [p - 0.001 for p in close_prices],
            "close": close_prices,
            "volume": [1000] * 50,
        }, index=dates)

        result = rsi(df, length=14)

        assert result is not None
        assert len(result) == len(df)
        # RSI should be between 0 and 100 (inclusive, with tolerance for float precision)
        valid_values = result.dropna()
        assert (valid_values >= -0.01).all()  # Small tolerance for float precision
        assert (valid_values <= 100.01).all()  # Small tolerance for float precision

    def test_macd_calculates(self, sample_ohlcv):
        """MACD shortcut should return DataFrame with multiple columns."""
        result = macd(sample_ohlcv, fast=12, slow=26, signal=9)

        assert result is not None
        assert isinstance(result, pd.DataFrame)
        # MACD returns multiple columns

    def test_bbands_calculates(self, sample_ohlcv):
        """Bollinger Bands shortcut should return DataFrame."""
        result = bbands(sample_ohlcv, length=20, std=2.0)

        assert result is not None
        assert isinstance(result, pd.DataFrame)

    def test_atr_calculates(self, sample_ohlcv):
        """ATR shortcut should calculate average true range."""
        result = atr(sample_ohlcv, length=14)

        assert result is not None
        # ATR should be positive
        valid_values = result.dropna()
        assert (valid_values >= 0).all()

    def test_stoch_calculates(self, sample_ohlcv):
        """Stochastic shortcut should return DataFrame."""
        result = stoch(sample_ohlcv, k=14, d=3, smooth_k=3)

        assert result is not None
        assert isinstance(result, pd.DataFrame)


# --- ensure_initialized Tests ---


class TestEnsureInitialized:
    """Tests for ensure_initialized function."""

    def test_initializes_once(self):
        """Should only initialize once."""
        # Reset the initialized flag
        pandas_ta_wrapper._initialized = False

        with patch("tradingsystem.indicators.pandas_ta_wrapper.register_pandas_ta_indicators") as mock_register:
            mock_register.return_value = 100

            ensure_initialized()
            ensure_initialized()  # Second call

            # Should only be called once
            assert mock_register.call_count == 1

    def test_sets_initialized_flag(self):
        """Should set _initialized to True."""
        pandas_ta_wrapper._initialized = False

        with patch("tradingsystem.indicators.pandas_ta_wrapper.register_pandas_ta_indicators") as mock_register:
            mock_register.return_value = 50

            ensure_initialized()

            assert pandas_ta_wrapper._initialized is True
