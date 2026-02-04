"""Tests for indicator registry."""

import pytest

from tradingsystem.indicators.base import BaseIndicator
from tradingsystem.indicators.registry import IndicatorRegistry


# --- Test Indicator ---


class MockIndicator(BaseIndicator):
    """Mock indicator for testing."""

    name = "Mock Indicator"
    description = "A mock indicator for testing"
    default_params = {"period": 10}

    def calculate(self, df, **params):
        return df["close"]


# --- Fixtures ---


@pytest.fixture(autouse=True)
def clean_registry():
    """Clear registry before and after each test."""
    # Store original state
    original_indicators = IndicatorRegistry._indicators.copy()
    original_pandas_ta = IndicatorRegistry._pandas_ta_indicators.copy()

    yield

    # Restore original state
    IndicatorRegistry._indicators = original_indicators
    IndicatorRegistry._pandas_ta_indicators = original_pandas_ta


# --- register decorator Tests ---


class TestRegisterDecorator:
    """Tests for @IndicatorRegistry.register decorator."""

    def test_registers_indicator(self):
        """Should register indicator class."""

        @IndicatorRegistry.register("test_indicator")
        class TestIndicator(BaseIndicator):
            name = "Test"

            def calculate(self, df, **params):
                return df["close"]

        assert IndicatorRegistry.get("test_indicator") is TestIndicator

    def test_lowercase_name(self):
        """Should store name in lowercase."""

        @IndicatorRegistry.register("MixedCase")
        class MixedIndicator(BaseIndicator):
            name = "Mixed"

            def calculate(self, df, **params):
                return df["close"]

        assert IndicatorRegistry.get("mixedcase") is MixedIndicator
        assert IndicatorRegistry.get("MIXEDCASE") is MixedIndicator


# --- register_pandas_ta Tests ---


class TestRegisterPandasTa:
    """Tests for register_pandas_ta method."""

    def test_registers_function(self):
        """Should register pandas-ta function."""
        mock_func = lambda df: df["close"]

        IndicatorRegistry.register_pandas_ta("test_ta", mock_func, "Test description")

        result = IndicatorRegistry.get_pandas_ta("test_ta")
        assert result is not None
        assert result["func"] is mock_func
        assert result["description"] == "Test description"

    def test_lowercase_name(self):
        """Should store name in lowercase."""
        mock_func = lambda df: df

        IndicatorRegistry.register_pandas_ta("MixedCase", mock_func)

        assert IndicatorRegistry.get_pandas_ta("mixedcase") is not None
        assert IndicatorRegistry.get_pandas_ta("MIXEDCASE") is not None

    def test_empty_description(self):
        """Should handle empty description."""
        mock_func = lambda df: df

        IndicatorRegistry.register_pandas_ta("no_desc", mock_func)

        result = IndicatorRegistry.get_pandas_ta("no_desc")
        assert result["description"] == ""


# --- get Tests ---


class TestGet:
    """Tests for get method."""

    def test_returns_registered_class(self):
        """Should return registered indicator class."""
        IndicatorRegistry._indicators["mock"] = MockIndicator

        result = IndicatorRegistry.get("mock")

        assert result is MockIndicator

    def test_returns_none_for_unknown(self):
        """Should return None for unknown indicator."""
        result = IndicatorRegistry.get("nonexistent")

        assert result is None

    def test_case_insensitive(self):
        """Should be case-insensitive."""
        IndicatorRegistry._indicators["myindicator"] = MockIndicator

        assert IndicatorRegistry.get("MYINDICATOR") is MockIndicator
        assert IndicatorRegistry.get("MyIndicator") is MockIndicator


# --- get_pandas_ta Tests ---


class TestGetPandasTa:
    """Tests for get_pandas_ta method."""

    def test_returns_registered_info(self):
        """Should return registered pandas-ta info."""
        mock_func = lambda df: df
        IndicatorRegistry._pandas_ta_indicators["sma"] = {
            "func": mock_func,
            "description": "Simple Moving Average",
        }

        result = IndicatorRegistry.get_pandas_ta("sma")

        assert result["func"] is mock_func
        assert result["description"] == "Simple Moving Average"

    def test_returns_none_for_unknown(self):
        """Should return None for unknown indicator."""
        result = IndicatorRegistry.get_pandas_ta("nonexistent")

        assert result is None


# --- is_registered Tests ---


class TestIsRegistered:
    """Tests for is_registered method."""

    def test_true_for_custom_indicator(self):
        """Should return True for registered custom indicator."""
        IndicatorRegistry._indicators["custom"] = MockIndicator

        assert IndicatorRegistry.is_registered("custom") is True

    def test_true_for_pandas_ta_indicator(self):
        """Should return True for registered pandas-ta indicator."""
        IndicatorRegistry._pandas_ta_indicators["sma"] = {"func": lambda x: x}

        assert IndicatorRegistry.is_registered("sma") is True

    def test_false_for_unknown(self):
        """Should return False for unknown indicator."""
        assert IndicatorRegistry.is_registered("unknown") is False

    def test_case_insensitive(self):
        """Should be case-insensitive."""
        IndicatorRegistry._indicators["myind"] = MockIndicator

        assert IndicatorRegistry.is_registered("MYIND") is True


# --- list_custom Tests ---


class TestListCustom:
    """Tests for list_custom method."""

    def test_returns_custom_names(self):
        """Should return list of custom indicator names."""
        IndicatorRegistry._indicators["ind1"] = MockIndicator
        IndicatorRegistry._indicators["ind2"] = MockIndicator

        result = IndicatorRegistry.list_custom()

        assert "ind1" in result
        assert "ind2" in result


# --- list_pandas_ta Tests ---


class TestListPandasTa:
    """Tests for list_pandas_ta method."""

    def test_returns_pandas_ta_names(self):
        """Should return list of pandas-ta indicator names."""
        IndicatorRegistry._pandas_ta_indicators["sma"] = {"func": lambda x: x}
        IndicatorRegistry._pandas_ta_indicators["ema"] = {"func": lambda x: x}

        result = IndicatorRegistry.list_pandas_ta()

        assert "sma" in result
        assert "ema" in result


# --- list_all Tests ---


class TestListAll:
    """Tests for list_all method."""

    def test_returns_both_types(self):
        """Should return dict with both indicator types."""
        IndicatorRegistry._indicators["custom1"] = MockIndicator
        IndicatorRegistry._pandas_ta_indicators["sma"] = {"func": lambda x: x}

        result = IndicatorRegistry.list_all()

        assert "custom" in result
        assert "pandas_ta" in result
        assert "custom1" in result["custom"]
        assert "sma" in result["pandas_ta"]


# --- get_info Tests ---


class TestGetInfo:
    """Tests for get_info method."""

    def test_returns_custom_indicator_info(self):
        """Should return info for custom indicator."""
        IndicatorRegistry._indicators["mock"] = MockIndicator

        result = IndicatorRegistry.get_info("mock")

        assert result is not None
        assert result["name"] == "mock"
        assert result["type"] == "custom"
        assert result["class"] == "MockIndicator"
        assert result["description"] == "A mock indicator for testing"
        assert result["default_params"] == {"period": 10}

    def test_returns_pandas_ta_indicator_info(self):
        """Should return info for pandas-ta indicator."""
        IndicatorRegistry._pandas_ta_indicators["sma"] = {
            "func": lambda x: x,
            "description": "Simple Moving Average",
        }

        result = IndicatorRegistry.get_info("sma")

        assert result is not None
        assert result["name"] == "sma"
        assert result["type"] == "pandas_ta"
        assert result["description"] == "Simple Moving Average"

    def test_returns_none_for_unknown(self):
        """Should return None for unknown indicator."""
        result = IndicatorRegistry.get_info("nonexistent")

        assert result is None

    def test_case_insensitive(self):
        """Should be case-insensitive."""
        IndicatorRegistry._indicators["mock"] = MockIndicator

        result = IndicatorRegistry.get_info("MOCK")

        assert result is not None
        assert result["name"] == "mock"


# --- clear Tests ---


class TestClear:
    """Tests for clear method."""

    def test_clears_all_indicators(self):
        """Should clear all registered indicators."""
        IndicatorRegistry._indicators["test"] = MockIndicator
        IndicatorRegistry._pandas_ta_indicators["sma"] = {"func": lambda x: x}

        IndicatorRegistry.clear()

        assert len(IndicatorRegistry._indicators) == 0
        assert len(IndicatorRegistry._pandas_ta_indicators) == 0
