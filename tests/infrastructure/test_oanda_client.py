"""Tests for OANDA trading client."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from tradingsystem.core.oanda_trading import (
    OandaAccount,
    OandaOrder,
    OandaOrderResponse,
    OandaTrade,
    OandaTradingClient,
)


@pytest.fixture
def client():
    """Create OANDA client for testing."""
    with patch("tradingsystem.core.oanda_trading.settings") as mock_settings:
        mock_settings.oanda_api_url = "https://api-fxpractice.oanda.com"
        mock_settings.oanda_account_id = "101-001-12345-001"
        mock_settings.oanda_api_key = "test-api-key"
        mock_settings.live_trading_enabled = True
        yield OandaTradingClient()


@pytest.fixture
def client_live_disabled():
    """Create OANDA client with live trading disabled."""
    with patch("tradingsystem.core.oanda_trading.settings") as mock_settings:
        mock_settings.oanda_api_url = "https://api-fxpractice.oanda.com"
        mock_settings.oanda_account_id = "101-001-12345-001"
        mock_settings.oanda_api_key = "test-api-key"
        mock_settings.live_trading_enabled = False
        yield OandaTradingClient()


@pytest.fixture
def mock_account_response():
    """Mock OANDA account response."""
    return {
        "account": {
            "id": "101-001-12345-001",
            "balance": "10000.00",
            "NAV": "10050.00",
            "unrealizedPL": "50.00",
            "marginUsed": "500.00",
            "marginAvailable": "9500.00",
            "openTradeCount": 2,
            "openPositionCount": 2,
        }
    }


@pytest.fixture
def mock_trades_response():
    """Mock OANDA open trades response."""
    return {
        "trades": [
            {
                "id": "trade-123",
                "instrument": "EUR_USD",
                "currentUnits": "1000",
                "price": "1.0850",
                "unrealizedPL": "25.00",
                "state": "OPEN",
                "openTime": "2024-01-15T12:00:00.000000000Z",
            }
        ]
    }


@pytest.fixture
def mock_order_fill_response():
    """Mock OANDA order fill response."""
    return {
        "orderFillTransaction": {
            "orderID": "order-456",
            "tradeOpened": {"tradeID": "trade-789"},
            "instrument": "EUR_USD",
            "units": "1000",
            "price": "1.0850",
            "time": "2024-01-15T12:00:00.000000000Z",
        }
    }


class TestOandaTradingClientInit:
    """Tests for OandaTradingClient initialization."""

    def test_client_uses_settings(self, client):
        """Should initialize with settings values."""
        assert client.account_id == "101-001-12345-001"
        assert "Bearer" in client.headers["Authorization"]


class TestGetAccountSummary:
    """Tests for OandaTradingClient.get_account_summary()."""

    @pytest.mark.asyncio
    async def test_get_account_summary_success(self, client, mock_account_response):
        """Should return OandaAccount on success."""
        # Create mock HTTP client with proper async response
        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = mock_account_response
        mock_response.raise_for_status = MagicMock()
        mock_http.get = AsyncMock(return_value=mock_response)

        # Patch _get_client as AsyncMock returning our mock HTTP client
        with patch.object(client, "_get_client", AsyncMock(return_value=mock_http)):
            account = await client.get_account_summary()

            assert isinstance(account, OandaAccount)
            assert account.id == "101-001-12345-001"
            assert account.balance == Decimal("10000.00")
            assert account.nav == Decimal("10050.00")

    @pytest.mark.asyncio
    async def test_get_account_summary_http_error(self, client):
        """Should raise on HTTP error."""
        mock_http = MagicMock()
        mock_http.get = AsyncMock(
            side_effect=httpx.HTTPStatusError("Unauthorized", request=MagicMock(), response=MagicMock())
        )

        with patch.object(client, "_get_client", AsyncMock(return_value=mock_http)):
            with pytest.raises(httpx.HTTPStatusError):
                await client.get_account_summary()


class TestGetOpenTrades:
    """Tests for OandaTradingClient.get_open_trades()."""

    @pytest.mark.asyncio
    async def test_get_open_trades_success(self, client, mock_trades_response):
        """Should return list of OandaTrade objects."""
        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = mock_trades_response
        mock_response.raise_for_status = MagicMock()
        mock_http.get = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_client", AsyncMock(return_value=mock_http)):
            trades = await client.get_open_trades()

            assert len(trades) == 1
            assert isinstance(trades[0], OandaTrade)
            assert trades[0].id == "trade-123"
            assert trades[0].instrument == "EUR_USD"

    @pytest.mark.asyncio
    async def test_get_open_trades_empty(self, client):
        """Should return empty list when no trades."""
        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"trades": []}
        mock_response.raise_for_status = MagicMock()
        mock_http.get = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_client", AsyncMock(return_value=mock_http)):
            trades = await client.get_open_trades()

            assert trades == []


class TestCreateMarketOrder:
    """Tests for OandaTradingClient.create_market_order()."""

    @pytest.mark.asyncio
    async def test_create_market_order_success(self, client, mock_order_fill_response):
        """Should return OandaOrderResponse on successful fill."""
        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = mock_order_fill_response
        mock_response.raise_for_status = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_client", AsyncMock(return_value=mock_http)):
            result = await client.create_market_order("EUR_USD", Decimal("1000"))

            assert isinstance(result, OandaOrderResponse)
            assert result.order_id == "order-456"
            assert result.trade_id == "trade-789"
            assert result.state == "FILLED"

    @pytest.mark.asyncio
    async def test_create_market_order_live_disabled(self, client_live_disabled):
        """Should raise RuntimeError when live trading disabled."""
        with pytest.raises(RuntimeError, match="Live trading is disabled"):
            await client_live_disabled.create_market_order("EUR_USD", Decimal("1000"))

    @pytest.mark.asyncio
    async def test_create_market_order_with_stops(self, client, mock_order_fill_response):
        """Should include stop loss and take profit in order."""
        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = mock_order_fill_response
        mock_response.raise_for_status = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_client", AsyncMock(return_value=mock_http)):
            await client.create_market_order(
                "EUR_USD",
                Decimal("1000"),
                stop_loss=Decimal("1.0800"),
                take_profit=Decimal("1.0900"),
            )

            call_kwargs = mock_http.post.call_args[1]
            order_data = call_kwargs["json"]["order"]
            assert "stopLossOnFill" in order_data
            assert "takeProfitOnFill" in order_data

    @pytest.mark.asyncio
    async def test_create_market_order_rejected(self, client):
        """Should raise RuntimeError when order rejected."""
        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "orderRejectTransaction": {"rejectReason": "INSUFFICIENT_MARGIN"}
        }
        mock_response.raise_for_status = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_client", AsyncMock(return_value=mock_http)):
            with pytest.raises(RuntimeError, match="Order rejected"):
                await client.create_market_order("EUR_USD", Decimal("1000000"))


class TestCloseTrade:
    """Tests for OandaTradingClient.close_trade()."""

    @pytest.mark.asyncio
    async def test_close_trade_success(self, client):
        """Should return OandaOrderResponse on successful close."""
        close_response = {
            "orderFillTransaction": {
                "orderID": "order-999",
                "instrument": "EUR_USD",
                "units": "-1000",
                "price": "1.0860",
                "time": "2024-01-15T13:00:00.000000000Z",
            }
        }

        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = close_response
        mock_response.raise_for_status = MagicMock()
        mock_http.put = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_client", AsyncMock(return_value=mock_http)):
            result = await client.close_trade("trade-123")

            assert isinstance(result, OandaOrderResponse)
            assert result.state == "FILLED"

    @pytest.mark.asyncio
    async def test_close_trade_live_disabled(self, client_live_disabled):
        """Should raise RuntimeError when live trading disabled."""
        with pytest.raises(RuntimeError, match="Live trading is disabled"):
            await client_live_disabled.close_trade("trade-123")


class TestCheckConnectivity:
    """Tests for OandaTradingClient.check_connectivity()."""

    @pytest.mark.asyncio
    async def test_check_connectivity_success(self, client, mock_account_response):
        """Should return connected status on success."""
        with patch.object(client, "get_account_summary") as mock_get_account:
            mock_get_account.return_value = OandaAccount(
                id="101-001-12345-001",
                balance=Decimal("10000.00"),
                nav=Decimal("10050.00"),
                unrealized_pnl=Decimal("50.00"),
                margin_used=Decimal("500.00"),
                margin_available=Decimal("9500.00"),
                open_trade_count=2,
                open_position_count=2,
            )

            result = await client.check_connectivity()

            assert result["connected"] is True
            assert result["account_id"] == "101-001-12345-001"

    @pytest.mark.asyncio
    async def test_check_connectivity_failure(self, client):
        """Should return disconnected status on error."""
        with patch.object(client, "get_account_summary") as mock_get_account:
            mock_get_account.side_effect = Exception("Connection refused")

            result = await client.check_connectivity()

            assert result["connected"] is False
            assert "Connection refused" in result["error"]


class TestOandaModels:
    """Tests for OANDA data models."""

    def test_oanda_account_parses_decimals(self):
        """Should parse monetary values as Decimal."""
        account = OandaAccount(
            id="test",
            balance=Decimal("10000.00"),
            nav=Decimal("10050.00"),
            unrealized_pnl=Decimal("50.00"),
            margin_used=Decimal("500.00"),
            margin_available=Decimal("9500.00"),
            open_trade_count=2,
            open_position_count=2,
        )

        assert isinstance(account.balance, Decimal)
        assert isinstance(account.nav, Decimal)

    def test_oanda_trade_parses_units_as_decimal(self):
        """Should parse units as Decimal."""
        trade = OandaTrade(
            id="trade-123",
            instrument="EUR_USD",
            units=Decimal("1000"),
            price=Decimal("1.0850"),
            unrealized_pnl=Decimal("25.00"),
            state="OPEN",
            open_time=datetime.now(timezone.utc),
        )

        assert isinstance(trade.units, Decimal)
        assert isinstance(trade.price, Decimal)

    def test_oanda_order_response_parses_correctly(self):
        """Should parse order response fields."""
        response = OandaOrderResponse(
            order_id="order-123",
            trade_id="trade-456",
            instrument="EUR_USD",
            units=Decimal("1000"),
            price=Decimal("1.0850"),
            time=datetime.now(timezone.utc),
            state="FILLED",
        )

        assert response.order_id == "order-123"
        assert response.trade_id == "trade-456"
        assert isinstance(response.units, Decimal)
