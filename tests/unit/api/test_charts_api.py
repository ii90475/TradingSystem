"""Tests for charts API endpoints."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from tradingsystem.api.charts import (
    create_chart,
    delete_chart,
    get_chart,
    get_chart_by_instrument,
    get_chart_candles,
    list_charts,
)
from tradingsystem.models.chart import Chart, ChartCreate


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
def sample_candles():
    """Create sample candles."""
    candle = MagicMock()
    candle.time = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)
    candle.open = Decimal("1.0850")
    candle.high = Decimal("1.0860")
    candle.low = Decimal("1.0840")
    candle.close = Decimal("1.0855")
    candle.volume = 1000
    return [candle]


# --- list_charts Tests ---


class TestListCharts:
    """Tests for list_charts endpoint."""

    @pytest.mark.asyncio
    async def test_returns_charts(self, sample_chart):
        """Should return list of charts."""
        with patch("tradingsystem.api.charts.chart_service") as mock_service:
            mock_service.list_charts = AsyncMock(return_value=[sample_chart])

            result = await list_charts()

            assert len(result) == 1
            assert result[0].instrument == "EUR_USD"

    @pytest.mark.asyncio
    async def test_returns_empty_list(self):
        """Should return empty list when no charts."""
        with patch("tradingsystem.api.charts.chart_service") as mock_service:
            mock_service.list_charts = AsyncMock(return_value=[])

            result = await list_charts()

            assert result == []


# --- create_chart Tests ---


class TestCreateChart:
    """Tests for create_chart endpoint."""

    @pytest.mark.asyncio
    async def test_creates_chart(self, sample_chart):
        """Should create and return chart."""
        with patch("tradingsystem.api.charts.chart_service") as mock_service:
            mock_service.create_chart = AsyncMock(return_value=sample_chart)

            chart_create = ChartCreate(instrument="EUR_USD", period="1h")
            result = await create_chart(chart_create)

            assert result.instrument == "EUR_USD"
            mock_service.create_chart.assert_called_once_with(chart_create)


# --- get_chart Tests ---


class TestGetChart:
    """Tests for get_chart endpoint."""

    @pytest.mark.asyncio
    async def test_returns_chart(self, sample_chart):
        """Should return chart by ID."""
        with patch("tradingsystem.api.charts.chart_service") as mock_service:
            mock_service.get_chart = AsyncMock(return_value=sample_chart)

            result = await get_chart(sample_chart.id)

            assert result.id == sample_chart.id

    @pytest.mark.asyncio
    async def test_raises_404_when_not_found(self):
        """Should raise 404 when chart not found."""
        with patch("tradingsystem.api.charts.chart_service") as mock_service:
            mock_service.get_chart = AsyncMock(return_value=None)

            with pytest.raises(HTTPException) as exc_info:
                await get_chart(uuid4())

            assert exc_info.value.status_code == 404
            assert "not found" in exc_info.value.detail.lower()


# --- delete_chart Tests ---


class TestDeleteChart:
    """Tests for delete_chart endpoint."""

    @pytest.mark.asyncio
    async def test_deletes_chart(self):
        """Should delete chart successfully."""
        with patch("tradingsystem.api.charts.chart_service") as mock_service:
            mock_service.delete_chart = AsyncMock(return_value=True)

            # Should not raise
            await delete_chart(uuid4())

            mock_service.delete_chart.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_404_when_not_found(self):
        """Should raise 404 when chart not found."""
        with patch("tradingsystem.api.charts.chart_service") as mock_service:
            mock_service.delete_chart = AsyncMock(return_value=False)

            with pytest.raises(HTTPException) as exc_info:
                await delete_chart(uuid4())

            assert exc_info.value.status_code == 404


# --- get_chart_candles Tests ---


class TestGetChartCandles:
    """Tests for get_chart_candles endpoint."""

    @pytest.mark.asyncio
    async def test_returns_candles(self, sample_chart, sample_candles):
        """Should return candles for chart."""
        with patch("tradingsystem.api.charts.chart_service") as mock_service:
            mock_service.get_chart = AsyncMock(return_value=sample_chart)
            mock_service.get_chart_candles = AsyncMock(return_value=sample_candles)

            result = await get_chart_candles(sample_chart.id)

            assert len(result) == 1
            mock_service.get_chart_candles.assert_called_once()

    @pytest.mark.asyncio
    async def test_passes_parameters(self, sample_chart, sample_candles):
        """Should pass start/end/limit parameters."""
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 31, tzinfo=timezone.utc)

        with patch("tradingsystem.api.charts.chart_service") as mock_service:
            mock_service.get_chart = AsyncMock(return_value=sample_chart)
            mock_service.get_chart_candles = AsyncMock(return_value=sample_candles)

            await get_chart_candles(sample_chart.id, start=start, end=end, limit=500)

            mock_service.get_chart_candles.assert_called_once_with(
                instrument=sample_chart.instrument,
                period=sample_chart.period,
                start=start,
                end=end,
                limit=500,
            )

    @pytest.mark.asyncio
    async def test_raises_404_when_chart_not_found(self):
        """Should raise 404 when chart not found."""
        with patch("tradingsystem.api.charts.chart_service") as mock_service:
            mock_service.get_chart = AsyncMock(return_value=None)

            with pytest.raises(HTTPException) as exc_info:
                await get_chart_candles(uuid4())

            assert exc_info.value.status_code == 404


# --- get_chart_by_instrument Tests ---


class TestGetChartByInstrument:
    """Tests for get_chart_by_instrument endpoint."""

    @pytest.mark.asyncio
    async def test_returns_chart(self, sample_chart):
        """Should return chart by instrument and period."""
        with patch("tradingsystem.api.charts.chart_service") as mock_service:
            mock_service.get_chart_by_instrument_period = AsyncMock(return_value=sample_chart)

            result = await get_chart_by_instrument("EUR_USD", period="1h")

            assert result.instrument == "EUR_USD"
            mock_service.get_chart_by_instrument_period.assert_called_once_with("EUR_USD", "1h")

    @pytest.mark.asyncio
    async def test_uses_provided_period(self, sample_chart):
        """Should use provided period."""
        with patch("tradingsystem.api.charts.chart_service") as mock_service:
            mock_service.get_chart_by_instrument_period = AsyncMock(return_value=sample_chart)

            await get_chart_by_instrument("EUR_USD", period="M5")

            mock_service.get_chart_by_instrument_period.assert_called_once_with("EUR_USD", "M5")

    @pytest.mark.asyncio
    async def test_auto_creates_chart_when_not_found(self, sample_chart):
        """Should auto-create chart when not found."""
        with patch("tradingsystem.api.charts.chart_service") as mock_service:
            mock_service.get_chart_by_instrument_period = AsyncMock(return_value=None)
            mock_service.create_chart = AsyncMock(return_value=sample_chart)

            result = await get_chart_by_instrument("EUR_USD", period="1h")

            # Should have created the chart
            mock_service.create_chart.assert_called_once()
            assert result.instrument == "EUR_USD"
