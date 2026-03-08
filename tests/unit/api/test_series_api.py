"""Tests for series API endpoints."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from tradingsystem.api.series import (
    create_series,
    delete_series,
    get_series,
    get_series_by_instrument,
    get_series_candles,
    list_series,
)
from tradingsystem.models.series import Series, SeriesCreate


# --- Fixtures ---


@pytest.fixture
def sample_series():
    """Create sample series."""
    return Series(
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


# --- list_series Tests ---


class TestListSeries:
    """Tests for list_series endpoint."""

    @pytest.mark.asyncio
    async def test_returns_series(self, sample_series):
        """Should return list of series."""
        with patch("tradingsystem.api.series.series_service") as mock_service:
            mock_service.list_series = AsyncMock(return_value=[sample_series])

            result = await list_series()

            assert len(result) == 1
            assert result[0].instrument == "EUR_USD"

    @pytest.mark.asyncio
    async def test_returns_empty_list(self):
        """Should return empty list when no series."""
        with patch("tradingsystem.api.series.series_service") as mock_service:
            mock_service.list_series = AsyncMock(return_value=[])

            result = await list_series()

            assert result == []


# --- create_series Tests ---


class TestCreateSeries:
    """Tests for create_series endpoint."""

    @pytest.mark.asyncio
    async def test_creates_series(self, sample_series):
        """Should create and return series."""
        with patch("tradingsystem.api.series.series_service") as mock_service:
            mock_service.create_series = AsyncMock(return_value=sample_series)

            series_create = SeriesCreate(instrument="EUR_USD", period="1h")
            result = await create_series(series_create)

            assert result.instrument == "EUR_USD"
            mock_service.create_series.assert_called_once_with(series_create)


# --- get_series Tests ---


class TestGetSeries:
    """Tests for get_series endpoint."""

    @pytest.mark.asyncio
    async def test_returns_series(self, sample_series):
        """Should return series by ID."""
        with patch("tradingsystem.api.series.series_service") as mock_service:
            mock_service.get_series = AsyncMock(return_value=sample_series)

            result = await get_series(sample_series.id)

            assert result.id == sample_series.id

    @pytest.mark.asyncio
    async def test_raises_404_when_not_found(self):
        """Should raise 404 when series not found."""
        with patch("tradingsystem.api.series.series_service") as mock_service:
            mock_service.get_series = AsyncMock(return_value=None)

            with pytest.raises(HTTPException) as exc_info:
                await get_series(uuid4())

            assert exc_info.value.status_code == 404
            assert "not found" in exc_info.value.detail.lower()


# --- delete_series Tests ---


class TestDeleteSeries:
    """Tests for delete_series endpoint."""

    @pytest.mark.asyncio
    async def test_deletes_series(self):
        """Should delete series successfully."""
        with patch("tradingsystem.api.series.series_service") as mock_service:
            mock_service.delete_series = AsyncMock(return_value=True)

            # Should not raise
            await delete_series(uuid4())

            mock_service.delete_series.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_404_when_not_found(self):
        """Should raise 404 when series not found."""
        with patch("tradingsystem.api.series.series_service") as mock_service:
            mock_service.delete_series = AsyncMock(return_value=False)

            with pytest.raises(HTTPException) as exc_info:
                await delete_series(uuid4())

            assert exc_info.value.status_code == 404


# --- get_series_candles Tests ---


class TestGetSeriesCandles:
    """Tests for get_series_candles endpoint."""

    @pytest.mark.asyncio
    async def test_returns_candles(self, sample_series, sample_candles):
        """Should return candles for series."""
        with patch("tradingsystem.api.series.series_service") as mock_service:
            mock_service.get_series = AsyncMock(return_value=sample_series)
            mock_service.get_series_candles = AsyncMock(return_value=sample_candles)

            result = await get_series_candles(sample_series.id)

            assert len(result) == 1
            mock_service.get_series_candles.assert_called_once()

    @pytest.mark.asyncio
    async def test_passes_parameters(self, sample_series, sample_candles):
        """Should pass start/end/limit parameters."""
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 31, tzinfo=timezone.utc)

        with patch("tradingsystem.api.series.series_service") as mock_service:
            mock_service.get_series = AsyncMock(return_value=sample_series)
            mock_service.get_series_candles = AsyncMock(return_value=sample_candles)

            await get_series_candles(sample_series.id, start=start, end=end, limit=500)

            mock_service.get_series_candles.assert_called_once_with(
                instrument=sample_series.instrument,
                period=sample_series.period,
                start=start,
                end=end,
                limit=500,
            )

    @pytest.mark.asyncio
    async def test_raises_404_when_series_not_found(self):
        """Should raise 404 when series not found."""
        with patch("tradingsystem.api.series.series_service") as mock_service:
            mock_service.get_series = AsyncMock(return_value=None)

            with pytest.raises(HTTPException) as exc_info:
                await get_series_candles(uuid4())

            assert exc_info.value.status_code == 404


# --- get_series_by_instrument Tests ---


class TestGetSeriesByInstrument:
    """Tests for get_series_by_instrument endpoint."""

    @pytest.mark.asyncio
    async def test_returns_series(self, sample_series):
        """Should return series by instrument and period."""
        with patch("tradingsystem.api.series.series_service") as mock_service:
            mock_service.get_series_by_instrument_period = AsyncMock(return_value=sample_series)

            result = await get_series_by_instrument("EUR_USD", period="1h")

            assert result.instrument == "EUR_USD"
            mock_service.get_series_by_instrument_period.assert_called_once_with("EUR_USD", "1h")

    @pytest.mark.asyncio
    async def test_uses_provided_period(self, sample_series):
        """Should use provided period."""
        with patch("tradingsystem.api.series.series_service") as mock_service:
            mock_service.get_series_by_instrument_period = AsyncMock(return_value=sample_series)

            await get_series_by_instrument("EUR_USD", period="M5")

            mock_service.get_series_by_instrument_period.assert_called_once_with("EUR_USD", "M5")

    @pytest.mark.asyncio
    async def test_auto_creates_series_when_not_found(self, sample_series):
        """Should auto-create series when not found."""
        with patch("tradingsystem.api.series.series_service") as mock_service:
            mock_service.get_series_by_instrument_period = AsyncMock(return_value=None)
            mock_service.create_series = AsyncMock(return_value=sample_series)

            result = await get_series_by_instrument("EUR_USD", period="1h")

            # Should have created the series
            mock_service.create_series.assert_called_once()
            assert result.instrument == "EUR_USD"
