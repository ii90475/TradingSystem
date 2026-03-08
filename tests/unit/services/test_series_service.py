"""Tests for series service."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pandas as pd
import pytest

from tradingsystem.core.rateservice import Candle
from tradingsystem.models.series import Series, SeriesCreate
from tradingsystem.services import series_service


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
def sample_series():
    """Create sample series data."""
    return {
        "id": uuid4(),
        "instrument": "EUR_USD",
        "period": "1h",
        "created_at": datetime.now(timezone.utc),
    }


@pytest.fixture
def sample_candles():
    """Create sample candle data."""
    return [
        Candle(
            time=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
            broker="oanda",
            pair="EUR_USD",
            open=Decimal("1.0850"),
            high=Decimal("1.0860"),
            low=Decimal("1.0840"),
            close=Decimal("1.0855"),
            volume=1000,
        ),
        Candle(
            time=datetime(2024, 1, 1, 13, 0, tzinfo=timezone.utc),
            broker="oanda",
            pair="EUR_USD",
            open=Decimal("1.0855"),
            high=Decimal("1.0870"),
            low=Decimal("1.0850"),
            close=Decimal("1.0865"),
            volume=1200,
        ),
    ]


# --- create_series Tests ---


class TestCreateSeries:
    """Tests for create_series function."""

    @pytest.mark.asyncio
    async def test_creates_series(self, mock_cursor, sample_series):
        """Should create series and return Series object."""
        mock_cursor.fetchone.return_value = sample_series

        with patch("tradingsystem.services.series_service.get_cursor") as mock_get:
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            series_create = SeriesCreate(instrument="EUR_USD", period="1h")
            result = await series_service.create_series(series_create)

            assert isinstance(result, Series)
            assert result.instrument == "EUR_USD"
            assert result.period == "1h"

    @pytest.mark.asyncio
    async def test_commits_transaction(self, mock_cursor, sample_series):
        """Should commit the transaction."""
        mock_cursor.fetchone.return_value = sample_series

        with patch("tradingsystem.services.series_service.get_cursor") as mock_get:
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            series_create = SeriesCreate(instrument="EUR_USD", period="1h")
            await series_service.create_series(series_create)

            mock_cursor.connection.commit.assert_called_once()


# --- get_series Tests ---


class TestGetSeries:
    """Tests for get_series function."""

    @pytest.mark.asyncio
    async def test_returns_series_when_found(self, mock_cursor, sample_series):
        """Should return Series when found."""
        mock_cursor.fetchone.return_value = sample_series

        with patch("tradingsystem.services.series_service.get_cursor") as mock_get:
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await series_service.get_series(sample_series["id"])

            assert isinstance(result, Series)
            assert result.id == sample_series["id"]

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, mock_cursor):
        """Should return None when not found."""
        mock_cursor.fetchone.return_value = None

        with patch("tradingsystem.services.series_service.get_cursor") as mock_get:
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await series_service.get_series(uuid4())

            assert result is None


# --- get_series_by_instrument_period Tests ---


class TestGetSeriesByInstrumentPeriod:
    """Tests for get_series_by_instrument_period function."""

    @pytest.mark.asyncio
    async def test_returns_series_when_found(self, mock_cursor, sample_series):
        """Should return Series when found."""
        mock_cursor.fetchone.return_value = sample_series

        with patch("tradingsystem.services.series_service.get_cursor") as mock_get:
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await series_service.get_series_by_instrument_period("EUR_USD", "1h")

            assert isinstance(result, Series)
            assert result.instrument == "EUR_USD"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, mock_cursor):
        """Should return None when not found."""
        mock_cursor.fetchone.return_value = None

        with patch("tradingsystem.services.series_service.get_cursor") as mock_get:
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await series_service.get_series_by_instrument_period("EUR_USD", "1h")

            assert result is None


# --- list_series Tests ---


class TestListSeries:
    """Tests for list_series function."""

    @pytest.mark.asyncio
    async def test_returns_list_of_series(self, mock_cursor, sample_series):
        """Should return list of Series objects."""
        mock_cursor.fetchall.return_value = [sample_series]

        with patch("tradingsystem.services.series_service.get_cursor") as mock_get:
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await series_service.list_series()

            assert len(result) == 1
            assert isinstance(result[0], Series)

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_none(self, mock_cursor):
        """Should return empty list when no series."""
        mock_cursor.fetchall.return_value = []

        with patch("tradingsystem.services.series_service.get_cursor") as mock_get:
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await series_service.list_series()

            assert result == []


# --- delete_series Tests ---


class TestDeleteSeries:
    """Tests for delete_series function."""

    @pytest.mark.asyncio
    async def test_returns_true_when_deleted(self, mock_cursor):
        """Should return True when series deleted."""
        mock_cursor.rowcount = 1

        with patch("tradingsystem.services.series_service.get_cursor") as mock_get:
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await series_service.delete_series(uuid4())

            assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(self, mock_cursor):
        """Should return False when series not found."""
        mock_cursor.rowcount = 0

        with patch("tradingsystem.services.series_service.get_cursor") as mock_get:
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await series_service.delete_series(uuid4())

            assert result is False


# --- get_series_candles Tests ---


class TestGetSeriesCandles:
    """Tests for get_series_candles function."""

    @pytest.mark.asyncio
    async def test_fetches_candles_from_rateservice(self, sample_candles):
        """Should fetch candles from RateService."""
        with patch("tradingsystem.services.series_service.rateservice_client") as mock_client:
            mock_client.get_candles = AsyncMock(return_value=sample_candles)

            result = await series_service.get_series_candles("EUR_USD", "1h")

            assert len(result) == 2
            mock_client.get_candles.assert_called_once()

    @pytest.mark.asyncio
    async def test_passes_all_parameters(self, sample_candles):
        """Should pass all parameters to RateService."""
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 31, tzinfo=timezone.utc)

        with patch("tradingsystem.services.series_service.rateservice_client") as mock_client:
            mock_client.get_candles = AsyncMock(return_value=sample_candles)

            await series_service.get_series_candles(
                instrument="EUR_USD",
                period="1h",
                start=start,
                end=end,
                limit=50,
            )

            mock_client.get_candles.assert_called_once_with(
                pair="EUR_USD",
                period="1h",
                start=start,
                end=end,
                limit=50,
            )


# --- get_series_dataframe Tests ---


class TestGetSeriesDataframe:
    """Tests for get_series_dataframe function."""

    @pytest.mark.asyncio
    async def test_returns_dataframe(self, sample_candles):
        """Should return pandas DataFrame."""
        with patch("tradingsystem.services.series_service.get_series_candles") as mock_get:
            mock_get.return_value = sample_candles

            result = await series_service.get_series_dataframe("EUR_USD", "1h")

            assert isinstance(result, pd.DataFrame)
            assert "open" in result.columns
            assert "high" in result.columns
            assert "low" in result.columns
            assert "close" in result.columns
            assert "volume" in result.columns

    @pytest.mark.asyncio
    async def test_converts_decimal_to_float(self, sample_candles):
        """Should convert Decimal values to float."""
        with patch("tradingsystem.services.series_service.get_series_candles") as mock_get:
            mock_get.return_value = sample_candles

            result = await series_service.get_series_dataframe("EUR_USD", "1h")

            assert result["close"].dtype in [float, "float64"]

    @pytest.mark.asyncio
    async def test_sets_time_as_index(self, sample_candles):
        """Should set time as DataFrame index."""
        with patch("tradingsystem.services.series_service.get_series_candles") as mock_get:
            mock_get.return_value = sample_candles

            result = await series_service.get_series_dataframe("EUR_USD", "1h")

            assert result.index.name == "time" or "time" not in result.columns

    @pytest.mark.asyncio
    async def test_returns_empty_dataframe_when_no_candles(self):
        """Should return empty DataFrame when no candles."""
        with patch("tradingsystem.services.series_service.get_series_candles") as mock_get:
            mock_get.return_value = []

            result = await series_service.get_series_dataframe("EUR_USD", "1h")

            assert isinstance(result, pd.DataFrame)
            assert len(result) == 0
            assert "open" in result.columns  # Should still have column names

    @pytest.mark.asyncio
    async def test_sorts_by_time(self, sample_candles):
        """Should sort DataFrame by time."""
        # Reverse the candles to test sorting
        reversed_candles = list(reversed(sample_candles))

        with patch("tradingsystem.services.series_service.get_series_candles") as mock_get:
            mock_get.return_value = reversed_candles

            result = await series_service.get_series_dataframe("EUR_USD", "1h")

            # Index should be sorted ascending
            assert result.index.is_monotonic_increasing
