"""Tests for charts API endpoints."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from tradingsystem.api.charts import (
    create_chart,
    delete_chart,
    get_chart,
    list_charts,
    list_charts_for_series,
    update_chart,
    ChartUpdate,
)
from tradingsystem.models.chart import Chart, ChartCreate, ChartDetail
from tradingsystem.models.series import Series


@pytest.fixture
def sample_series():
    """Create sample series."""
    return Series(
        id=uuid4(),
        instrument="EUR_USD",
        period="H1",
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_chart(sample_series):
    """Create sample chart."""
    return Chart(
        id=uuid4(),
        name="Euro Scalper",
        series_id=sample_series.id,
        created_at=datetime.now(timezone.utc),
    )


class TestListCharts:
    """Tests for list_charts endpoint."""

    @pytest.mark.asyncio
    async def test_returns_charts(self, sample_series, sample_chart):
        """Should return all charts with series info."""
        chart_detail = ChartDetail(
            id=sample_chart.id,
            name=sample_chart.name,
            series_id=sample_chart.series_id,
            instrument=sample_series.instrument,
            period=sample_series.period,
            created_at=sample_chart.created_at,
        )
        with patch("tradingsystem.api.charts.chart_service") as mock_service:
            mock_service.list_charts = AsyncMock(return_value=[chart_detail])

            result = await list_charts()

            assert len(result) == 1
            assert result[0].name == "Euro Scalper"
            assert result[0].instrument == "EUR_USD"


class TestCreateChart:
    """Tests for create_chart endpoint."""

    @pytest.mark.asyncio
    async def test_creates_chart(self, sample_series, sample_chart):
        """Should create chart when series exists."""
        with patch("tradingsystem.api.charts.series_service") as mock_series, \
             patch("tradingsystem.api.charts.chart_service") as mock_chart:
            mock_series.get_series = AsyncMock(return_value=sample_series)
            mock_chart.create_chart = AsyncMock(return_value=sample_chart)

            chart_create = ChartCreate(name="Euro Scalper", series_id=sample_series.id)
            result = await create_chart(chart_create)

            assert result.name == "Euro Scalper"

    @pytest.mark.asyncio
    async def test_raises_404_when_series_not_found(self):
        """Should raise 404 when series not found."""
        with patch("tradingsystem.api.charts.series_service") as mock_series:
            mock_series.get_series = AsyncMock(return_value=None)

            chart_create = ChartCreate(name="Test", series_id=uuid4())

            with pytest.raises(HTTPException) as exc_info:
                await create_chart(chart_create)

            assert exc_info.value.status_code == 404


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


class TestUpdateChart:
    """Tests for update_chart endpoint."""

    @pytest.mark.asyncio
    async def test_updates_chart(self, sample_chart):
        """Should update chart name."""
        updated = Chart(
            id=sample_chart.id,
            name="New Name",
            series_id=sample_chart.series_id,
            created_at=sample_chart.created_at,
        )
        with patch("tradingsystem.api.charts.chart_service") as mock_service:
            mock_service.update_chart = AsyncMock(return_value=updated)

            result = await update_chart(sample_chart.id, ChartUpdate(name="New Name"))

            assert result.name == "New Name"

    @pytest.mark.asyncio
    async def test_raises_404_when_not_found(self):
        """Should raise 404 when chart not found."""
        with patch("tradingsystem.api.charts.chart_service") as mock_service:
            mock_service.update_chart = AsyncMock(return_value=None)

            with pytest.raises(HTTPException) as exc_info:
                await update_chart(uuid4(), ChartUpdate(name="Test"))

            assert exc_info.value.status_code == 404


class TestDeleteChart:
    """Tests for delete_chart endpoint."""

    @pytest.mark.asyncio
    async def test_deletes_chart(self):
        """Should delete chart."""
        with patch("tradingsystem.api.charts.chart_service") as mock_service:
            mock_service.delete_chart = AsyncMock(return_value=True)

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


class TestListChartsForSeries:
    """Tests for list_charts_for_series endpoint."""

    @pytest.mark.asyncio
    async def test_returns_charts(self, sample_series, sample_chart):
        """Should return charts for series."""
        with patch("tradingsystem.api.charts.series_service") as mock_series, \
             patch("tradingsystem.api.charts.chart_service") as mock_chart:
            mock_series.get_series = AsyncMock(return_value=sample_series)
            mock_chart.list_charts_for_series = AsyncMock(return_value=[sample_chart])

            result = await list_charts_for_series(sample_series.id)

            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_raises_404_when_series_not_found(self):
        """Should raise 404 when series not found."""
        with patch("tradingsystem.api.charts.series_service") as mock_series:
            mock_series.get_series = AsyncMock(return_value=None)

            with pytest.raises(HTTPException) as exc_info:
                await list_charts_for_series(uuid4())

            assert exc_info.value.status_code == 404
