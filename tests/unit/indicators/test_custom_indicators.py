"""Tests for custom indicators."""

from datetime import timezone

import numpy as np
import pandas as pd
import pytest

from tradingsystem.indicators.custom.momentum import CustomMomentum
from tradingsystem.indicators.custom.price_action import HighLowRange, PriceChange


# --- Fixtures ---


@pytest.fixture
def sample_df():
    """Create sample OHLCV DataFrame."""
    dates = pd.date_range(start="2024-01-01", periods=20, freq="1h", tz=timezone.utc)
    return pd.DataFrame({
        "open": [1.0850 + i * 0.001 for i in range(20)],
        "high": [1.0860 + i * 0.001 for i in range(20)],
        "low": [1.0840 + i * 0.001 for i in range(20)],
        "close": [1.0855 + i * 0.001 for i in range(20)],
        "volume": [1000 + i * 10 for i in range(20)],
    }, index=dates)


@pytest.fixture
def volatile_df():
    """Create DataFrame with price fluctuations."""
    dates = pd.date_range(start="2024-01-01", periods=20, freq="1h", tz=timezone.utc)
    # Oscillating prices
    close = [1.0850 + 0.01 * (i % 3 - 1) for i in range(20)]
    return pd.DataFrame({
        "open": [p - 0.001 for p in close],
        "high": [p + 0.002 for p in close],
        "low": [p - 0.002 for p in close],
        "close": close,
        "volume": [1000] * 20,
    }, index=dates)


# --- CustomMomentum Tests ---


class TestCustomMomentum:
    """Tests for CustomMomentum indicator."""

    def test_metadata(self):
        """Should have correct metadata."""
        indicator = CustomMomentum()

        assert indicator.name == "Custom Momentum"
        assert "momentum" in indicator.description.lower()
        assert indicator.default_params == {"period": 14}

    def test_calculate_returns_series(self, sample_df):
        """Should return pandas Series."""
        indicator = CustomMomentum()

        result = indicator.calculate(sample_df, period=5)

        assert isinstance(result, pd.Series)
        assert len(result) == len(sample_df)

    def test_calculate_momentum_values(self, sample_df):
        """Should calculate percentage change."""
        indicator = CustomMomentum()

        result = indicator.calculate(sample_df, period=1)

        # First value should be NaN (no previous value)
        assert pd.isna(result.iloc[0])
        # Subsequent values should be positive (prices increasing)
        assert result.iloc[5] > 0

    def test_momentum_clipped_to_range(self):
        """Should clip values to -100 to +100."""
        # Create extreme price movement
        dates = pd.date_range(start="2024-01-01", periods=5, freq="1h", tz=timezone.utc)
        df = pd.DataFrame({
            "open": [1.0, 1.0, 1.0, 1.0, 1.0],
            "high": [1.1, 1.1, 1.1, 1.1, 10.0],  # Extreme high
            "low": [0.9, 0.9, 0.9, 0.9, 0.9],
            "close": [1.0, 1.0, 1.0, 1.0, 5.0],  # 400% increase
            "volume": [1000] * 5,
        }, index=dates)

        indicator = CustomMomentum()
        result = indicator.calculate(df, period=1)

        # Should be clipped to 100
        assert result.iloc[-1] == 100

    def test_validates_dataframe(self):
        """Should validate DataFrame has required columns."""
        df = pd.DataFrame({"close": [1, 2, 3]})
        indicator = CustomMomentum()

        with pytest.raises(ValueError, match="missing required columns"):
            indicator.calculate(df)

    def test_uses_default_period(self, sample_df):
        """Should use default period when not specified."""
        indicator = CustomMomentum()

        # Should not raise
        result = indicator.calculate(sample_df)

        assert isinstance(result, pd.Series)


# --- PriceChange Tests ---


class TestPriceChange:
    """Tests for PriceChange indicator."""

    def test_metadata(self):
        """Should have correct metadata."""
        indicator = PriceChange()

        assert indicator.name == "Price Change"
        assert indicator.default_params == {"period": 1}

    def test_calculate_returns_dataframe(self, sample_df):
        """Should return DataFrame with change columns."""
        indicator = PriceChange()

        result = indicator.calculate(sample_df, period=1)

        assert isinstance(result, pd.DataFrame)
        assert "change" in result.columns
        assert "change_pct" in result.columns

    def test_absolute_change(self, sample_df):
        """Should calculate absolute price change."""
        indicator = PriceChange()

        result = indicator.calculate(sample_df, period=1)

        # First value is NaN
        assert pd.isna(result["change"].iloc[0])
        # Change should be positive (prices increasing)
        assert result["change"].iloc[1] > 0

    def test_percentage_change(self, sample_df):
        """Should calculate percentage change."""
        indicator = PriceChange()

        result = indicator.calculate(sample_df, period=1)

        # Percentage should be calculated correctly
        valid_pct = result["change_pct"].dropna()
        assert len(valid_pct) > 0

    def test_multi_period_change(self, sample_df):
        """Should calculate change over multiple periods."""
        indicator = PriceChange()

        result = indicator.calculate(sample_df, period=5)

        # First 5 values should be NaN
        assert result["change"].iloc[:5].isna().all()
        assert result["change_pct"].iloc[:5].isna().all()

    def test_validates_dataframe(self):
        """Should validate DataFrame."""
        df = pd.DataFrame({"close": [1, 2, 3]})
        indicator = PriceChange()

        with pytest.raises(ValueError, match="missing required columns"):
            indicator.calculate(df)


# --- HighLowRange Tests ---


class TestHighLowRange:
    """Tests for HighLowRange indicator."""

    def test_metadata(self):
        """Should have correct metadata."""
        indicator = HighLowRange()

        assert indicator.name == "High-Low Range"
        assert indicator.default_params == {"period": 1}

    def test_calculate_returns_dataframe(self, sample_df):
        """Should return DataFrame with range columns."""
        indicator = HighLowRange()

        result = indicator.calculate(sample_df, period=1)

        assert isinstance(result, pd.DataFrame)
        assert "range" in result.columns
        assert "range_pct" in result.columns

    def test_single_candle_range(self, sample_df):
        """Should calculate single candle high-low range."""
        indicator = HighLowRange()

        result = indicator.calculate(sample_df, period=1)

        # Range should be high - low for each candle
        expected_range = sample_df["high"] - sample_df["low"]
        pd.testing.assert_series_equal(result["range"], expected_range, check_names=False)

    def test_range_percentage(self, sample_df):
        """Should calculate range as percentage of close."""
        indicator = HighLowRange()

        result = indicator.calculate(sample_df, period=1)

        # Range % should be (high-low)/close * 100
        expected_pct = ((sample_df["high"] - sample_df["low"]) / sample_df["close"]) * 100
        pd.testing.assert_series_equal(result["range_pct"], expected_pct, check_names=False)

    def test_rolling_range(self, sample_df):
        """Should calculate rolling range over period."""
        indicator = HighLowRange()

        result = indicator.calculate(sample_df, period=5)

        # First 4 values should be NaN (rolling window not full)
        assert result["range"].iloc[:4].isna().all()
        # Value at index 4 should be max(high[0:5]) - min(low[0:5])
        expected = sample_df["high"].iloc[:5].max() - sample_df["low"].iloc[:5].min()
        assert abs(result["range"].iloc[4] - expected) < 0.0001

    def test_validates_dataframe(self):
        """Should validate DataFrame."""
        df = pd.DataFrame({"close": [1, 2, 3]})
        indicator = HighLowRange()

        with pytest.raises(ValueError, match="missing required columns"):
            indicator.calculate(df)

    def test_range_always_positive(self, volatile_df):
        """Should always return positive range values."""
        indicator = HighLowRange()

        result = indicator.calculate(volatile_df, period=1)

        valid_range = result["range"].dropna()
        assert (valid_range >= 0).all()
