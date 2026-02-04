"""Tests for base indicator class."""

from datetime import timezone

import pandas as pd
import pytest

from tradingsystem.indicators.base import BaseIndicator


# --- Test Indicator Implementation ---


class TestIndicator(BaseIndicator):
    """Concrete implementation for testing."""

    name = "Test Indicator"
    description = "A test indicator"
    default_params = {"period": 14, "threshold": 0.5}

    def calculate(self, df: pd.DataFrame, **params) -> pd.Series:
        """Simple test calculation."""
        return df["close"] * params.get("multiplier", 1)


# --- Fixtures ---


@pytest.fixture
def indicator():
    """Create test indicator."""
    return TestIndicator()


@pytest.fixture
def sample_df():
    """Create sample OHLCV DataFrame."""
    dates = pd.date_range(start="2024-01-01", periods=10, freq="1h", tz=timezone.utc)
    return pd.DataFrame({
        "open": [1.0850 + i * 0.0001 for i in range(10)],
        "high": [1.0860 + i * 0.0001 for i in range(10)],
        "low": [1.0840 + i * 0.0001 for i in range(10)],
        "close": [1.0855 + i * 0.0001 for i in range(10)],
        "volume": [1000 + i * 10 for i in range(10)],
    }, index=dates)


# --- BaseIndicator Tests ---


class TestBaseIndicatorGetParams:
    """Tests for get_params method."""

    def test_returns_defaults(self, indicator):
        """Should return default params when no overrides."""
        params = indicator.get_params()

        assert params["period"] == 14
        assert params["threshold"] == 0.5

    def test_applies_overrides(self, indicator):
        """Should apply overrides to defaults."""
        params = indicator.get_params(period=20)

        assert params["period"] == 20
        assert params["threshold"] == 0.5

    def test_adds_new_params(self, indicator):
        """Should add new params not in defaults."""
        params = indicator.get_params(new_param="value")

        assert params["new_param"] == "value"
        assert params["period"] == 14

    def test_does_not_modify_defaults(self, indicator):
        """Should not modify the default_params dict."""
        original = indicator.default_params.copy()

        indicator.get_params(period=999)

        assert indicator.default_params == original


class TestBaseIndicatorValidateDataframe:
    """Tests for validate_dataframe method."""

    def test_passes_valid_dataframe(self, indicator, sample_df):
        """Should not raise for valid DataFrame."""
        # Should not raise
        indicator.validate_dataframe(sample_df)

    def test_raises_for_missing_open(self, indicator, sample_df):
        """Should raise ValueError for missing open column."""
        df = sample_df.drop(columns=["open"])

        with pytest.raises(ValueError, match="missing required columns"):
            indicator.validate_dataframe(df)

    def test_raises_for_missing_high(self, indicator, sample_df):
        """Should raise ValueError for missing high column."""
        df = sample_df.drop(columns=["high"])

        with pytest.raises(ValueError, match="missing required columns"):
            indicator.validate_dataframe(df)

    def test_raises_for_missing_low(self, indicator, sample_df):
        """Should raise ValueError for missing low column."""
        df = sample_df.drop(columns=["low"])

        with pytest.raises(ValueError, match="missing required columns"):
            indicator.validate_dataframe(df)

    def test_raises_for_missing_close(self, indicator, sample_df):
        """Should raise ValueError for missing close column."""
        df = sample_df.drop(columns=["close"])

        with pytest.raises(ValueError, match="missing required columns"):
            indicator.validate_dataframe(df)

    def test_raises_for_multiple_missing(self, indicator):
        """Should raise ValueError listing all missing columns."""
        df = pd.DataFrame({"close": [1, 2, 3], "volume": [100, 200, 300]})

        with pytest.raises(ValueError, match="missing required columns"):
            indicator.validate_dataframe(df)

    def test_allows_extra_columns(self, indicator, sample_df):
        """Should allow extra columns beyond required."""
        df = sample_df.copy()
        df["extra_col"] = 1

        # Should not raise
        indicator.validate_dataframe(df)


class TestBaseIndicatorRepr:
    """Tests for __repr__ method."""

    def test_includes_class_name(self, indicator):
        """Should include class name in repr."""
        result = repr(indicator)

        assert "TestIndicator" in result

    def test_includes_indicator_name(self, indicator):
        """Should include indicator name in repr."""
        result = repr(indicator)

        assert "Test Indicator" in result

    def test_format(self, indicator):
        """Should follow expected format."""
        result = repr(indicator)

        assert result == "TestIndicator(name='Test Indicator')"


class TestBaseIndicatorCalculate:
    """Tests for calculate method."""

    def test_calculate_returns_series(self, indicator, sample_df):
        """Should return Series from calculate."""
        result = indicator.calculate(sample_df, multiplier=2)

        assert isinstance(result, pd.Series)
        assert len(result) == len(sample_df)

    def test_calculate_uses_params(self, indicator, sample_df):
        """Should use provided params."""
        result = indicator.calculate(sample_df, multiplier=2)

        expected = sample_df["close"] * 2
        pd.testing.assert_series_equal(result, expected)
