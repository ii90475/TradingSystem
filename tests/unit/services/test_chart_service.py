"""Tests for chart service."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from tradingsystem.models.chart import Chart, ChartCreate
from tradingsystem.services import chart_service


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
def sample_chart_row():
    """Create sample chart data."""
    return {
        "id": uuid4(),
        "name": "Euro Scalper",
        "series_id": uuid4(),
        "created_at": datetime.now(timezone.utc),
    }


class TestCreateChart:
    """Tests for create_chart function."""

    @pytest.mark.asyncio
    async def test_creates_chart(self, mock_cursor, sample_chart_row):
        """Should create a chart linked to a series."""
        mock_cursor.fetchone.return_value = sample_chart_row

        with patch("tradingsystem.services.chart_service.get_cursor") as mock_get:
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            chart_create = ChartCreate(
                name="Euro Scalper",
                series_id=sample_chart_row["series_id"],
            )
            result = await chart_service.create_chart(chart_create)

            assert isinstance(result, Chart)
            assert result.name == "Euro Scalper"
            assert result.series_id == sample_chart_row["series_id"]


class TestGetChart:
    """Tests for get_chart function."""

    @pytest.mark.asyncio
    async def test_returns_chart(self, mock_cursor, sample_chart_row):
        """Should return chart by ID."""
        mock_cursor.fetchone.return_value = sample_chart_row

        with patch("tradingsystem.services.chart_service.get_cursor") as mock_get:
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await chart_service.get_chart(sample_chart_row["id"])

            assert isinstance(result, Chart)
            assert result.id == sample_chart_row["id"]

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, mock_cursor):
        """Should return None when chart not found."""
        mock_cursor.fetchone.return_value = None

        with patch("tradingsystem.services.chart_service.get_cursor") as mock_get:
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await chart_service.get_chart(uuid4())

            assert result is None


class TestListCharts:
    """Tests for list_charts function."""

    @pytest.mark.asyncio
    async def test_returns_charts(self, mock_cursor, sample_chart_row):
        """Should return list of charts."""
        mock_cursor.fetchall.return_value = [sample_chart_row]

        with patch("tradingsystem.services.chart_service.get_cursor") as mock_get:
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await chart_service.list_charts()

            assert len(result) == 1
            assert isinstance(result[0], Chart)

    @pytest.mark.asyncio
    async def test_returns_empty_list(self, mock_cursor):
        """Should return empty list when no charts."""
        mock_cursor.fetchall.return_value = []

        with patch("tradingsystem.services.chart_service.get_cursor") as mock_get:
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await chart_service.list_charts()

            assert result == []


class TestListChartsForSeries:
    """Tests for list_charts_for_series function."""

    @pytest.mark.asyncio
    async def test_returns_charts_for_series(self, mock_cursor, sample_chart_row):
        """Should return charts for a given series."""
        mock_cursor.fetchall.return_value = [sample_chart_row]

        with patch("tradingsystem.services.chart_service.get_cursor") as mock_get:
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await chart_service.list_charts_for_series(sample_chart_row["series_id"])

            assert len(result) == 1


class TestUpdateChart:
    """Tests for update_chart function."""

    @pytest.mark.asyncio
    async def test_updates_name(self, mock_cursor, sample_chart_row):
        """Should update chart name."""
        updated = {**sample_chart_row, "name": "New Name"}
        mock_cursor.fetchone.return_value = updated

        with patch("tradingsystem.services.chart_service.get_cursor") as mock_get:
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await chart_service.update_chart(sample_chart_row["id"], "New Name")

            assert result.name == "New Name"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, mock_cursor):
        """Should return None when chart not found."""
        mock_cursor.fetchone.return_value = None

        with patch("tradingsystem.services.chart_service.get_cursor") as mock_get:
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await chart_service.update_chart(uuid4(), "New Name")

            assert result is None


class TestDeleteChart:
    """Tests for delete_chart function."""

    @pytest.mark.asyncio
    async def test_returns_true_when_deleted(self, mock_cursor):
        """Should return True when chart deleted."""
        mock_cursor.rowcount = 1

        with patch("tradingsystem.services.chart_service.get_cursor") as mock_get:
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await chart_service.delete_chart(uuid4())

            assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(self, mock_cursor):
        """Should return False when chart not found."""
        mock_cursor.rowcount = 0

        with patch("tradingsystem.services.chart_service.get_cursor") as mock_get:
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await chart_service.delete_chart(uuid4())

            assert result is False
