"""Tests for indicators API endpoints."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from tradingsystem.api.indicators import (
    add_indicator_to_chart,
    calculate_indicator,
    delete_chart_indicator,
    get_chart_indicators,
    get_indicator_info,
    list_available_indicators,
)
from tradingsystem.models.chart import Chart, ChartIndicator, ChartIndicatorCreate


# --- Fixtures ---


@pytest.fixture
def sample_chart():
    """Create sample chart."""
    return Chart(
        id=uuid4(),
        instrument="EUR_USD",
        period="1h",
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_indicator():
    """Create sample chart indicator."""
    return ChartIndicator(
        id=uuid4(),
        chart_id=uuid4(),
        indicator_type="sma",
        parameters={"length": 20},
        created_at=datetime.now(timezone.utc),
    )


# --- list_available_indicators Tests ---


class TestListAvailableIndicators:
    """Tests for list_available_indicators endpoint."""

    @pytest.mark.asyncio
    async def test_returns_indicators(self):
        """Should return available indicators."""
        mock_result = {
            "custom": [{"name": "custom1", "description": "Custom indicator"}],
            "pandas_ta": [{"name": "sma", "description": "Simple Moving Average"}],
        }

        with patch("tradingsystem.api.indicators.indicator_service") as mock_service:
            mock_service.list_available_indicators.return_value = mock_result

            result = await list_available_indicators()

            assert "custom" in result
            assert "pandas_ta" in result


# --- get_indicator_info Tests ---


class TestGetIndicatorInfo:
    """Tests for get_indicator_info endpoint."""

    @pytest.mark.asyncio
    async def test_returns_info(self):
        """Should return indicator info."""
        mock_info = {"name": "sma", "description": "Simple Moving Average", "params": {"length": 20}}

        with patch("tradingsystem.api.indicators.indicator_service") as mock_service:
            mock_service.get_indicator_info.return_value = mock_info

            result = await get_indicator_info("sma")

            assert result["name"] == "sma"

    @pytest.mark.asyncio
    async def test_raises_404_when_not_found(self):
        """Should raise 404 when indicator not found."""
        with patch("tradingsystem.api.indicators.indicator_service") as mock_service:
            mock_service.get_indicator_info.return_value = None

            with pytest.raises(HTTPException) as exc_info:
                await get_indicator_info("unknown")

            assert exc_info.value.status_code == 404
            assert "not found" in exc_info.value.detail.lower()


# --- calculate_indicator Tests ---


class TestCalculateIndicator:
    """Tests for calculate_indicator endpoint."""

    @pytest.mark.asyncio
    async def test_calculates_indicator(self):
        """Should calculate and return indicator values."""
        mock_result = {
            "indicator": "sma",
            "params": {"length": 20},
            "values": [{"time": "2024-01-15T12:00:00Z", "value": 1.0850}],
        }

        with patch("tradingsystem.api.indicators.indicator_service") as mock_service:
            mock_service.calculate_indicator = AsyncMock(return_value=mock_result)

            result = await calculate_indicator(
                instrument="EUR_USD",
                period="1h",
                indicator_type="sma",
                limit=100,
                start=None,
                end=None,
                params=None,
            )

            assert result.indicator == "sma"
            assert len(result.values) == 1

    @pytest.mark.asyncio
    async def test_parses_json_params(self):
        """Should parse JSON params string."""
        mock_result = {
            "indicator": "sma",
            "params": {"length": 50},
            "values": [],
        }

        with patch("tradingsystem.api.indicators.indicator_service") as mock_service:
            mock_service.calculate_indicator = AsyncMock(return_value=mock_result)

            await calculate_indicator(
                instrument="EUR_USD",
                period="1h",
                indicator_type="sma",
                limit=100,
                params='{"length": 50}',
            )

            call_kwargs = mock_service.calculate_indicator.call_args[1]
            assert call_kwargs["params"] == {"length": 50}

    @pytest.mark.asyncio
    async def test_raises_400_for_invalid_json(self):
        """Should raise 400 for invalid JSON params."""
        with pytest.raises(HTTPException) as exc_info:
            await calculate_indicator(
                instrument="EUR_USD",
                period="1h",
                indicator_type="sma",
                limit=100,
                params="invalid json",
            )

        assert exc_info.value.status_code == 400
        assert "Invalid JSON" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_raises_400_for_calculation_error(self):
        """Should raise 400 when calculation fails."""
        with patch("tradingsystem.api.indicators.indicator_service") as mock_service:
            mock_service.calculate_indicator = AsyncMock(
                side_effect=ValueError("Failed to calculate")
            )

            with pytest.raises(HTTPException) as exc_info:
                await calculate_indicator(
                    instrument="EUR_USD",
                    period="1h",
                    indicator_type="invalid",
                    limit=100,
                    start=None,
                    end=None,
                    params=None,
                )

            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_passes_time_parameters(self):
        """Should pass start/end time parameters."""
        mock_result = {"indicator": "sma", "params": {}, "values": []}
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 31, tzinfo=timezone.utc)

        with patch("tradingsystem.api.indicators.indicator_service") as mock_service:
            mock_service.calculate_indicator = AsyncMock(return_value=mock_result)

            await calculate_indicator(
                instrument="EUR_USD",
                period="1h",
                indicator_type="sma",
                limit=100,
                start=start,
                end=end,
                params=None,
            )

            call_kwargs = mock_service.calculate_indicator.call_args[1]
            assert call_kwargs["start"] == start
            assert call_kwargs["end"] == end


# --- get_chart_indicators Tests ---


class TestGetChartIndicators:
    """Tests for get_chart_indicators endpoint."""

    @pytest.mark.asyncio
    async def test_returns_indicators(self, sample_chart, sample_indicator):
        """Should return chart indicators."""
        with patch("tradingsystem.api.indicators.chart_service") as mock_chart, \
             patch("tradingsystem.api.indicators.indicator_service") as mock_indicator:
            mock_chart.get_chart = AsyncMock(return_value=sample_chart)
            mock_indicator.get_chart_indicators = AsyncMock(return_value=[sample_indicator])

            result = await get_chart_indicators(sample_chart.id)

            assert len(result) == 1
            assert result[0].indicator_type == "sma"

    @pytest.mark.asyncio
    async def test_raises_404_when_chart_not_found(self):
        """Should raise 404 when chart not found."""
        with patch("tradingsystem.api.indicators.chart_service") as mock_chart:
            mock_chart.get_chart = AsyncMock(return_value=None)

            with pytest.raises(HTTPException) as exc_info:
                await get_chart_indicators(uuid4())

            assert exc_info.value.status_code == 404


# --- add_indicator_to_chart Tests ---


class TestAddIndicatorToChart:
    """Tests for add_indicator_to_chart endpoint."""

    @pytest.mark.asyncio
    async def test_adds_indicator(self, sample_chart, sample_indicator):
        """Should add indicator to chart."""
        with patch("tradingsystem.api.indicators.chart_service") as mock_chart, \
             patch("tradingsystem.api.indicators.indicator_service") as mock_indicator:
            mock_chart.get_chart = AsyncMock(return_value=sample_chart)
            mock_indicator.add_indicator_to_chart = AsyncMock(return_value=sample_indicator)

            indicator_create = ChartIndicatorCreate(
                indicator_type="sma",
                parameters={"length": 20},
            )
            result = await add_indicator_to_chart(sample_chart.id, indicator_create)

            assert result.indicator_type == "sma"

    @pytest.mark.asyncio
    async def test_raises_404_when_chart_not_found(self):
        """Should raise 404 when chart not found."""
        with patch("tradingsystem.api.indicators.chart_service") as mock_chart:
            mock_chart.get_chart = AsyncMock(return_value=None)

            indicator_create = ChartIndicatorCreate(indicator_type="sma", parameters={})

            with pytest.raises(HTTPException) as exc_info:
                await add_indicator_to_chart(uuid4(), indicator_create)

            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_raises_400_for_invalid_indicator(self, sample_chart):
        """Should raise 400 for invalid indicator."""
        with patch("tradingsystem.api.indicators.chart_service") as mock_chart, \
             patch("tradingsystem.api.indicators.indicator_service") as mock_indicator:
            mock_chart.get_chart = AsyncMock(return_value=sample_chart)
            mock_indicator.add_indicator_to_chart = AsyncMock(
                side_effect=ValueError("Unknown indicator")
            )

            indicator_create = ChartIndicatorCreate(indicator_type="unknown", parameters={})

            with pytest.raises(HTTPException) as exc_info:
                await add_indicator_to_chart(sample_chart.id, indicator_create)

            assert exc_info.value.status_code == 400


# --- delete_chart_indicator Tests ---


class TestDeleteChartIndicator:
    """Tests for delete_chart_indicator endpoint."""

    @pytest.mark.asyncio
    async def test_deletes_indicator(self):
        """Should delete indicator."""
        with patch("tradingsystem.api.indicators.indicator_service") as mock_service:
            mock_service.delete_chart_indicator = AsyncMock(return_value=True)

            # Should not raise
            await delete_chart_indicator(uuid4())

            mock_service.delete_chart_indicator.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_404_when_not_found(self):
        """Should raise 404 when indicator not found."""
        with patch("tradingsystem.api.indicators.indicator_service") as mock_service:
            mock_service.delete_chart_indicator = AsyncMock(return_value=False)

            with pytest.raises(HTTPException) as exc_info:
                await delete_chart_indicator(uuid4())

            assert exc_info.value.status_code == 404
