"""Tests for RateService client."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from tradingsystem.core.rateservice import (
    Candle,
    CurrentRate,
    RateServiceClient,
)


@pytest.fixture
def client():
    """Create RateService client for testing."""
    return RateServiceClient(base_url="http://localhost:8000")


@pytest.fixture
def mock_rate_response():
    """Mock rate response data."""
    return {
        "pair": "EUR_USD",
        "bid": "1.0850",
        "ask": "1.0852",
        "time": "2024-01-15T12:00:00Z",
        "tradeable": True,
    }


@pytest.fixture
def mock_candle_response():
    """Mock candle response data."""
    return [
        {
            "time": "2024-01-15T12:00:00Z",
            "broker": "oanda",
            "pair": "EUR_USD",
            "open": "1.0850",
            "high": "1.0860",
            "low": "1.0845",
            "close": "1.0855",
            "volume": 1000,
        }
    ]


def create_mock_response(json_data, status_code=200):
    """Create a mock httpx Response."""
    mock_response = MagicMock()
    mock_response.json.return_value = json_data
    mock_response.status_code = status_code
    mock_response.raise_for_status = MagicMock()
    return mock_response


class TestGetCurrentRate:
    """Tests for RateServiceClient.get_current_rate()."""

    @pytest.mark.asyncio
    async def test_get_current_rate_success(self, client, mock_rate_response):
        """Should return CurrentRate on success."""
        mock_response = create_mock_response(mock_rate_response)

        with patch("tradingsystem.core.rateservice.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

            rate = await client.get_current_rate("EUR_USD")

            assert isinstance(rate, CurrentRate)
            assert rate.pair == "EUR_USD"
            assert rate.bid == Decimal("1.0850")
            assert rate.ask == Decimal("1.0852")

    @pytest.mark.asyncio
    async def test_get_current_rate_http_error(self, client):
        """Should raise on HTTP error."""
        # Patch where httpx.AsyncClient is used, not where it's defined
        with patch("tradingsystem.core.rateservice.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(
                side_effect=httpx.HTTPStatusError("Not found", request=MagicMock(), response=MagicMock())
            )
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(httpx.HTTPStatusError):
                await client.get_current_rate("INVALID")

    @pytest.mark.asyncio
    async def test_get_current_rate_timeout(self, client):
        """Should raise on timeout."""
        with patch("tradingsystem.core.rateservice.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(httpx.TimeoutException):
                await client.get_current_rate("EUR_USD")


class TestGetCurrentRates:
    """Tests for RateServiceClient.get_current_rates()."""

    @pytest.mark.asyncio
    async def test_get_current_rates_success(self, client, mock_rate_response):
        """Should return list of CurrentRate objects."""
        mock_response = create_mock_response([mock_rate_response])

        with patch("tradingsystem.core.rateservice.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

            rates = await client.get_current_rates(["EUR_USD"])

            assert len(rates) == 1
            assert isinstance(rates[0], CurrentRate)

    @pytest.mark.asyncio
    async def test_get_current_rates_no_pairs(self, client, mock_rate_response):
        """Should get all rates when pairs not specified."""
        mock_response = create_mock_response([mock_rate_response, mock_rate_response])

        with patch("tradingsystem.core.rateservice.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

            rates = await client.get_current_rates()

            assert len(rates) == 2


class TestGetCandles:
    """Tests for RateServiceClient.get_candles()."""

    @pytest.mark.asyncio
    async def test_get_candles_success(self, client, mock_candle_response):
        """Should return list of Candle objects."""
        mock_response = create_mock_response(mock_candle_response)

        with patch("tradingsystem.core.rateservice.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

            candles = await client.get_candles("EUR_USD")

            assert len(candles) == 1
            assert isinstance(candles[0], Candle)
            assert candles[0].pair == "EUR_USD"

    @pytest.mark.asyncio
    async def test_get_candles_m1_uses_history_endpoint(self, client, mock_candle_response):
        """Should use history endpoint for M1 period."""
        mock_response = create_mock_response(mock_candle_response)

        with patch("tradingsystem.core.rateservice.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

            await client.get_candles("EUR_USD", period="M1")

            call_url = mock_client.get.call_args[0][0]
            assert "/history" in call_url

    @pytest.mark.asyncio
    async def test_get_candles_other_period_uses_candles_endpoint(self, client, mock_candle_response):
        """Should use candles endpoint for non-M1 periods."""
        mock_response = create_mock_response(mock_candle_response)

        with patch("tradingsystem.core.rateservice.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

            await client.get_candles("EUR_USD", period="1h")

            call_url = mock_client.get.call_args[0][0]
            assert "/candles/1h" in call_url

    @pytest.mark.asyncio
    async def test_get_candles_with_time_range(self, client, mock_candle_response):
        """Should pass start and end parameters."""
        mock_response = create_mock_response(mock_candle_response)

        with patch("tradingsystem.core.rateservice.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

            start = datetime(2024, 1, 1, tzinfo=timezone.utc)
            end = datetime(2024, 1, 15, tzinfo=timezone.utc)

            await client.get_candles("EUR_USD", start=start, end=end)

            call_kwargs = mock_client.get.call_args[1]
            assert "start" in call_kwargs["params"]
            assert "end" in call_kwargs["params"]


class TestGetPairs:
    """Tests for RateServiceClient.get_pairs()."""

    @pytest.mark.asyncio
    async def test_get_pairs_success(self, client):
        """Should return list of pair strings."""
        mock_response = create_mock_response(["EUR_USD", "GBP_USD", "USD_JPY"])

        with patch("tradingsystem.core.rateservice.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

            pairs = await client.get_pairs()

            assert pairs == ["EUR_USD", "GBP_USD", "USD_JPY"]


class TestCheckHealth:
    """Tests for RateServiceClient.check_health()."""

    @pytest.mark.asyncio
    async def test_check_health_healthy(self, client):
        """Should return healthy status."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "healthy"}

        with patch("tradingsystem.core.rateservice.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client.check_health()

            assert result["healthy"] is True
            assert result["status"] == "healthy"
            assert result["error"] is None

    @pytest.mark.asyncio
    async def test_check_health_degraded(self, client):
        """Should return healthy=True for degraded status."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "degraded"}

        with patch("tradingsystem.core.rateservice.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client.check_health()

            assert result["healthy"] is True
            assert result["status"] == "degraded"

    @pytest.mark.asyncio
    async def test_check_health_http_error(self, client):
        """Should return unhealthy on HTTP error."""
        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch("tradingsystem.core.rateservice.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client.check_health()

            assert result["healthy"] is False
            assert "500" in result["error"]

    @pytest.mark.asyncio
    async def test_check_health_connection_error(self, client):
        """Should return unhealthy on connection error."""
        with patch("tradingsystem.core.rateservice.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client.check_health()

            assert result["healthy"] is False
            assert result["status"] == "unreachable"
            assert "Connection refused" in result["error"]


class TestCurrentRateModel:
    """Tests for CurrentRate model."""

    def test_current_rate_parses_decimals(self):
        """Should parse bid/ask as Decimal."""
        rate = CurrentRate(
            pair="EUR_USD",
            bid=Decimal("1.0850"),
            ask=Decimal("1.0852"),
            time=datetime.now(timezone.utc),
        )

        assert isinstance(rate.bid, Decimal)
        assert isinstance(rate.ask, Decimal)

    def test_current_rate_default_tradeable(self):
        """Should default tradeable to True."""
        rate = CurrentRate(
            pair="EUR_USD",
            bid=Decimal("1.0850"),
            ask=Decimal("1.0852"),
            time=datetime.now(timezone.utc),
        )

        assert rate.tradeable is True


class TestCandleModel:
    """Tests for Candle model."""

    def test_candle_parses_ohlc_as_decimal(self):
        """Should parse OHLC values as Decimal."""
        candle = Candle(
            time=datetime.now(timezone.utc),
            broker="oanda",
            pair="EUR_USD",
            open=Decimal("1.0850"),
            high=Decimal("1.0860"),
            low=Decimal("1.0845"),
            close=Decimal("1.0855"),
            volume=1000,
        )

        assert isinstance(candle.open, Decimal)
        assert isinstance(candle.high, Decimal)
        assert isinstance(candle.low, Decimal)
        assert isinstance(candle.close, Decimal)
