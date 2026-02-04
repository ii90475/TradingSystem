"""Tests for chart service."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pandas as pd
import pytest

from tradingsystem.core.rateservice import Candle
from tradingsystem.models.chart import Chart, ChartCreate
from tradingsystem.services import chart_service


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
def sample_chart():
    """Create sample chart data."""
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


# --- create_chart Tests ---


class TestCreateChart:
    """Tests for create_chart function."""

    @pytest.mark.asyncio
    async def test_creates_chart(self, mock_cursor, sample_chart):
        """Should create chart and return Chart object."""
        mock_cursor.fetchone.return_value = sample_chart

        with patch("tradingsystem.services.chart_service.get_cursor") as mock_get:
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            chart_create = ChartCreate(instrument="EUR_USD", period="1h")
            result = await chart_service.create_chart(chart_create)

            assert isinstance(result, Chart)
            assert result.instrument == "EUR_USD"
            assert result.period == "1h"

    @pytest.mark.asyncio
    async def test_commits_transaction(self, mock_cursor, sample_chart):
        """Should commit the transaction."""
        mock_cursor.fetchone.return_value = sample_chart

        with patch("tradingsystem.services.chart_service.get_cursor") as mock_get:
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            chart_create = ChartCreate(instrument="EUR_USD", period="1h")
            await chart_service.create_chart(chart_create)

            mock_cursor.connection.commit.assert_called_once()


# --- get_chart Tests ---


class TestGetChart:
    """Tests for get_chart function."""

    @pytest.mark.asyncio
    async def test_returns_chart_when_found(self, mock_cursor, sample_chart):
        """Should return Chart when found."""
        mock_cursor.fetchone.return_value = sample_chart

        with patch("tradingsystem.services.chart_service.get_cursor") as mock_get:
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await chart_service.get_chart(sample_chart["id"])

            assert isinstance(result, Chart)
            assert result.id == sample_chart["id"]

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, mock_cursor):
        """Should return None when not found."""
        mock_cursor.fetchone.return_value = None

        with patch("tradingsystem.services.chart_service.get_cursor") as mock_get:
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await chart_service.get_chart(uuid4())

            assert result is None


# --- get_chart_by_instrument_period Tests ---


class TestGetChartByInstrumentPeriod:
    """Tests for get_chart_by_instrument_period function."""

    @pytest.mark.asyncio
    async def test_returns_chart_when_found(self, mock_cursor, sample_chart):
        """Should return Chart when found."""
        mock_cursor.fetchone.return_value = sample_chart

        with patch("tradingsystem.services.chart_service.get_cursor") as mock_get:
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await chart_service.get_chart_by_instrument_period("EUR_USD", "1h")

            assert isinstance(result, Chart)
            assert result.instrument == "EUR_USD"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, mock_cursor):
        """Should return None when not found."""
        mock_cursor.fetchone.return_value = None

        with patch("tradingsystem.services.chart_service.get_cursor") as mock_get:
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await chart_service.get_chart_by_instrument_period("EUR_USD", "1h")

            assert result is None


# --- list_charts Tests ---


class TestListCharts:
    """Tests for list_charts function."""

    @pytest.mark.asyncio
    async def test_returns_list_of_charts(self, mock_cursor, sample_chart):
        """Should return list of Chart objects."""
        mock_cursor.fetchall.return_value = [sample_chart]

        with patch("tradingsystem.services.chart_service.get_cursor") as mock_get:
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await chart_service.list_charts()

            assert len(result) == 1
            assert isinstance(result[0], Chart)

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_none(self, mock_cursor):
        """Should return empty list when no charts."""
        mock_cursor.fetchall.return_value = []

        with patch("tradingsystem.services.chart_service.get_cursor") as mock_get:
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await chart_service.list_charts()

            assert result == []


# --- delete_chart Tests ---


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


# --- get_chart_candles Tests ---


class TestGetChartCandles:
    """Tests for get_chart_candles function."""

    @pytest.mark.asyncio
    async def test_fetches_candles_from_rateservice(self, sample_candles):
        """Should fetch candles from RateService."""
        with patch("tradingsystem.services.chart_service.rateservice_client") as mock_client:
            mock_client.get_candles = AsyncMock(return_value=sample_candles)

            result = await chart_service.get_chart_candles("EUR_USD", "1h")

            assert len(result) == 2
            mock_client.get_candles.assert_called_once()

    @pytest.mark.asyncio
    async def test_passes_all_parameters(self, sample_candles):
        """Should pass all parameters to RateService."""
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 31, tzinfo=timezone.utc)

        with patch("tradingsystem.services.chart_service.rateservice_client") as mock_client:
            mock_client.get_candles = AsyncMock(return_value=sample_candles)

            await chart_service.get_chart_candles(
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


# --- get_chart_dataframe Tests ---


class TestGetChartDataframe:
    """Tests for get_chart_dataframe function."""

    @pytest.mark.asyncio
    async def test_returns_dataframe(self, sample_candles):
        """Should return pandas DataFrame."""
        with patch("tradingsystem.services.chart_service.get_chart_candles") as mock_get:
            mock_get.return_value = sample_candles

            result = await chart_service.get_chart_dataframe("EUR_USD", "1h")

            assert isinstance(result, pd.DataFrame)
            assert "open" in result.columns
            assert "high" in result.columns
            assert "low" in result.columns
            assert "close" in result.columns
            assert "volume" in result.columns

    @pytest.mark.asyncio
    async def test_converts_decimal_to_float(self, sample_candles):
        """Should convert Decimal values to float."""
        with patch("tradingsystem.services.chart_service.get_chart_candles") as mock_get:
            mock_get.return_value = sample_candles

            result = await chart_service.get_chart_dataframe("EUR_USD", "1h")

            assert result["close"].dtype in [float, "float64"]

    @pytest.mark.asyncio
    async def test_sets_time_as_index(self, sample_candles):
        """Should set time as DataFrame index."""
        with patch("tradingsystem.services.chart_service.get_chart_candles") as mock_get:
            mock_get.return_value = sample_candles

            result = await chart_service.get_chart_dataframe("EUR_USD", "1h")

            assert result.index.name == "time" or "time" not in result.columns

    @pytest.mark.asyncio
    async def test_returns_empty_dataframe_when_no_candles(self):
        """Should return empty DataFrame when no candles."""
        with patch("tradingsystem.services.chart_service.get_chart_candles") as mock_get:
            mock_get.return_value = []

            result = await chart_service.get_chart_dataframe("EUR_USD", "1h")

            assert isinstance(result, pd.DataFrame)
            assert len(result) == 0
            assert "open" in result.columns  # Should still have column names

    @pytest.mark.asyncio
    async def test_sorts_by_time(self, sample_candles):
        """Should sort DataFrame by time."""
        # Reverse the candles to test sorting
        reversed_candles = list(reversed(sample_candles))

        with patch("tradingsystem.services.chart_service.get_chart_candles") as mock_get:
            mock_get.return_value = reversed_candles

            result = await chart_service.get_chart_dataframe("EUR_USD", "1h")

            # Index should be sorted ascending
            assert result.index.is_monotonic_increasing
