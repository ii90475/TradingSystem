"""Tests for indicator service."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pandas as pd
import pytest

from tradingsystem.models.series import SeriesIndicator, SeriesIndicatorCreate
from tradingsystem.services import indicator_service


# --- Fixtures ---


@pytest.fixture
def mock_cursor():
    """Create a mock database cursor."""
    cursor = AsyncMock()
    cursor.fetchone = AsyncMock()
    cursor.fetchall = AsyncMock()
    cursor.execute = AsyncMock()
    cursor.rowcount = 0
    cursor.connection = AsyncMock()
    cursor.connection.commit = AsyncMock()
    return cursor


@pytest.fixture
def sample_indicator():
    """Create sample indicator data."""
    return {
        "id": uuid4(),
        "series_id": uuid4(),
        "indicator_type": "sma",
        "parameters": {"length": 20},
        "created_at": datetime.now(timezone.utc),
    }


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


# --- add_indicator_to_series Tests ---


class TestAddIndicatorToSeries:
    """Tests for add_indicator_to_series function."""

    @pytest.mark.asyncio
    async def test_adds_indicator(self, mock_cursor, sample_indicator):
        """Should add indicator to chart."""
        mock_cursor.fetchone.return_value = sample_indicator

        with patch("tradingsystem.services.indicator_service.get_cursor") as mock_get, \
             patch("tradingsystem.services.indicator_service.ensure_initialized"), \
             patch("tradingsystem.services.indicator_service.IndicatorRegistry") as mock_registry:
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_registry.is_registered.return_value = True

            series_id = uuid4()
            indicator = SeriesIndicatorCreate(
                indicator_type="sma",
                parameters={"length": 20},
            )

            result = await indicator_service.add_indicator_to_series(series_id, indicator)

            assert isinstance(result, SeriesIndicator)
            assert result.indicator_type == "sma"

    @pytest.mark.asyncio
    async def test_raises_for_unknown_indicator(self, mock_cursor):
        """Should raise ValueError for unknown indicator."""
        with patch("tradingsystem.services.indicator_service.ensure_initialized"), \
             patch("tradingsystem.services.indicator_service.IndicatorRegistry") as mock_registry:
            mock_registry.is_registered.return_value = False

            series_id = uuid4()
            indicator = SeriesIndicatorCreate(
                indicator_type="unknown_indicator",
                parameters={},
            )

            with pytest.raises(ValueError, match="Unknown indicator"):
                await indicator_service.add_indicator_to_series(series_id, indicator)


# --- get_series_indicators Tests ---


class TestGetSeriesIndicators:
    """Tests for get_series_indicators function."""

    @pytest.mark.asyncio
    async def test_returns_indicators(self, mock_cursor, sample_indicator):
        """Should return list of ChartIndicator objects."""
        mock_cursor.fetchall.return_value = [sample_indicator]

        with patch("tradingsystem.services.indicator_service.get_cursor") as mock_get:
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await indicator_service.get_series_indicators(sample_indicator["series_id"])

            assert len(result) == 1
            assert isinstance(result[0], SeriesIndicator)

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_none(self, mock_cursor):
        """Should return empty list when no indicators."""
        mock_cursor.fetchall.return_value = []

        with patch("tradingsystem.services.indicator_service.get_cursor") as mock_get:
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await indicator_service.get_series_indicators(uuid4())

            assert result == []


# --- delete_series_indicator Tests ---


class TestDeleteSeriesIndicator:
    """Tests for delete_series_indicator function."""

    @pytest.mark.asyncio
    async def test_returns_true_when_deleted(self, mock_cursor):
        """Should return True when indicator deleted."""
        mock_cursor.rowcount = 1

        with patch("tradingsystem.services.indicator_service.get_cursor") as mock_get:
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await indicator_service.delete_series_indicator(uuid4())

            assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(self, mock_cursor):
        """Should return False when indicator not found."""
        mock_cursor.rowcount = 0

        with patch("tradingsystem.services.indicator_service.get_cursor") as mock_get:
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await indicator_service.delete_series_indicator(uuid4())

            assert result is False


# --- calculate_indicator Tests ---


class TestCalculateIndicator:
    """Tests for calculate_indicator function."""

    @pytest.mark.asyncio
    async def test_calculates_custom_indicator(self, sample_ohlcv):
        """Should calculate custom indicator from registry."""
        mock_indicator = MagicMock()
        mock_indicator.calculate.return_value = pd.Series([1.0] * 50, index=sample_ohlcv.index)

        with patch("tradingsystem.services.indicator_service.ensure_initialized"), \
             patch("tradingsystem.services.indicator_service.series_service") as mock_chart, \
             patch("tradingsystem.services.indicator_service.IndicatorRegistry") as mock_registry:
            mock_chart.get_series_dataframe = AsyncMock(return_value=sample_ohlcv)
            mock_registry.get.return_value = lambda: mock_indicator

            result = await indicator_service.calculate_indicator(
                instrument="EUR_USD",
                period="1h",
                indicator_type="custom_indicator",
            )

            assert result["indicator"] == "custom_indicator"
            assert len(result["values"]) == 50

    @pytest.mark.asyncio
    async def test_calculates_pandas_ta_indicator(self, sample_ohlcv):
        """Should calculate pandas-ta indicator."""
        with patch("tradingsystem.services.indicator_service.ensure_initialized"), \
             patch("tradingsystem.services.indicator_service.series_service") as mock_chart, \
             patch("tradingsystem.services.indicator_service.IndicatorRegistry") as mock_registry, \
             patch("tradingsystem.services.indicator_service.calculate_pandas_ta_indicator") as mock_calc:
            mock_chart.get_series_dataframe = AsyncMock(return_value=sample_ohlcv)
            mock_registry.get.return_value = None  # Not a custom indicator
            mock_calc.return_value = pd.Series([1.0] * 50, index=sample_ohlcv.index)

            result = await indicator_service.calculate_indicator(
                instrument="EUR_USD",
                period="1h",
                indicator_type="sma",
                params={"length": 20},
            )

            assert result["indicator"] == "sma"
            mock_calc.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_empty_values_when_no_data(self):
        """Should return empty values when no candle data."""
        with patch("tradingsystem.services.indicator_service.ensure_initialized"), \
             patch("tradingsystem.services.indicator_service.series_service") as mock_chart:
            mock_chart.get_series_dataframe = AsyncMock(return_value=pd.DataFrame())

            result = await indicator_service.calculate_indicator(
                instrument="EUR_USD",
                period="1h",
                indicator_type="sma",
            )

            assert result["values"] == []

    @pytest.mark.asyncio
    async def test_raises_when_calculation_fails(self, sample_ohlcv):
        """Should raise ValueError when calculation fails."""
        with patch("tradingsystem.services.indicator_service.ensure_initialized"), \
             patch("tradingsystem.services.indicator_service.series_service") as mock_chart, \
             patch("tradingsystem.services.indicator_service.IndicatorRegistry") as mock_registry, \
             patch("tradingsystem.services.indicator_service.calculate_pandas_ta_indicator") as mock_calc:
            mock_chart.get_series_dataframe = AsyncMock(return_value=sample_ohlcv)
            mock_registry.get.return_value = None
            mock_calc.return_value = None  # Calculation failed

            with pytest.raises(ValueError, match="Failed to calculate"):
                await indicator_service.calculate_indicator(
                    instrument="EUR_USD",
                    period="1h",
                    indicator_type="invalid",
                )

    @pytest.mark.asyncio
    async def test_handles_dataframe_result(self, sample_ohlcv):
        """Should handle DataFrame result (multi-column indicator)."""
        result_df = pd.DataFrame({
            "upper": [1.1] * 50,
            "middle": [1.0] * 50,
            "lower": [0.9] * 50,
        }, index=sample_ohlcv.index)

        with patch("tradingsystem.services.indicator_service.ensure_initialized"), \
             patch("tradingsystem.services.indicator_service.series_service") as mock_chart, \
             patch("tradingsystem.services.indicator_service.IndicatorRegistry") as mock_registry, \
             patch("tradingsystem.services.indicator_service.calculate_pandas_ta_indicator") as mock_calc:
            mock_chart.get_series_dataframe = AsyncMock(return_value=sample_ohlcv)
            mock_registry.get.return_value = None
            mock_calc.return_value = result_df

            result = await indicator_service.calculate_indicator(
                instrument="EUR_USD",
                period="1h",
                indicator_type="bbands",
            )

            assert len(result["values"]) == 50
            assert "upper" in result["values"][0]
            assert "middle" in result["values"][0]
            assert "lower" in result["values"][0]


# --- list_available_indicators Tests ---


class TestListAvailableIndicators:
    """Tests for list_available_indicators function."""

    def test_returns_custom_and_pandas_ta(self):
        """Should return both custom and pandas-ta indicators."""
        with patch("tradingsystem.services.indicator_service.ensure_initialized"), \
             patch("tradingsystem.services.indicator_service.IndicatorRegistry") as mock_registry:
            mock_registry.list_custom.return_value = ["custom1", "custom2"]
            mock_registry.list_pandas_ta.return_value = ["sma", "ema"]
            mock_registry.get_info.return_value = {"name": "test", "description": "Test"}

            result = indicator_service.list_available_indicators()

            assert "custom" in result
            assert "pandas_ta" in result
            assert len(result["custom"]) == 2
            assert len(result["pandas_ta"]) == 2

    def test_handles_missing_info(self):
        """Should handle indicators with no info."""
        with patch("tradingsystem.services.indicator_service.ensure_initialized"), \
             patch("tradingsystem.services.indicator_service.IndicatorRegistry") as mock_registry:
            mock_registry.list_custom.return_value = ["custom1"]
            mock_registry.list_pandas_ta.return_value = []
            mock_registry.get_info.return_value = None

            result = indicator_service.list_available_indicators()

            # Should skip indicators with no info
            assert result["custom"] == []


# --- get_indicator_info Tests ---


class TestGetIndicatorInfo:
    """Tests for get_indicator_info function."""

    def test_returns_indicator_info(self):
        """Should return info for known indicator."""
        info = {"name": "sma", "description": "Simple Moving Average"}

        with patch("tradingsystem.services.indicator_service.ensure_initialized"), \
             patch("tradingsystem.services.indicator_service.IndicatorRegistry") as mock_registry:
            mock_registry.get_info.return_value = info

            result = indicator_service.get_indicator_info("sma")

            assert result == info

    def test_returns_none_for_unknown(self):
        """Should return None for unknown indicator."""
        with patch("tradingsystem.services.indicator_service.ensure_initialized"), \
             patch("tradingsystem.services.indicator_service.IndicatorRegistry") as mock_registry:
            mock_registry.get_info.return_value = None

            result = indicator_service.get_indicator_info("unknown")

            assert result is None
