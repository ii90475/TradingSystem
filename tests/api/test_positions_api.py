"""API tests for the Positions endpoints."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from tradingsystem.main import app
from tradingsystem.models.order import Order, OrderSide, OrderStatus, OrderType
from tradingsystem.models.position import Position, PositionSide, PositionStatus, PositionSummary


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def sample_position():
    """Create a sample position for testing."""
    return Position(
        id=uuid4(),
        instrument="EUR_USD",
        side=PositionSide.LONG,
        quantity=Decimal("1000"),
        entry_price=Decimal("1.0850"),
        entry_time=datetime.now(timezone.utc),
        exit_price=None,
        exit_time=None,
        status=PositionStatus.OPEN,
        strategy_id="test_strategy",
        pnl=None,
        pnl_percent=None,
    )


@pytest.fixture
def closed_position():
    """Create a closed position for testing."""
    return Position(
        id=uuid4(),
        instrument="EUR_USD",
        side=PositionSide.LONG,
        quantity=Decimal("1000"),
        entry_price=Decimal("1.0850"),
        entry_time=datetime.now(timezone.utc),
        exit_price=Decimal("1.0900"),
        exit_time=datetime.now(timezone.utc),
        status=PositionStatus.CLOSED,
        strategy_id="test_strategy",
        pnl=Decimal("50.00"),
        pnl_percent=Decimal("0.46"),
    )


@pytest.fixture
def sample_order():
    """Create a sample order for testing."""
    return Order(
        id=uuid4(),
        external_id=None,
        strategy_id="test_strategy",
        instrument="EUR_USD",
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        quantity=Decimal("1000"),
        price=None,
        status=OrderStatus.FILLED,
        created_at=datetime.now(timezone.utc),
        filled_at=datetime.now(timezone.utc),
        filled_price=Decimal("1.0900"),
        filled_quantity=Decimal("1000"),
    )


class TestListPositions:
    """Tests for GET /positions."""

    def test_list_positions_success(self, client, sample_position):
        """Should return list of positions."""
        with patch("tradingsystem.api.positions.position_service") as mock_service:
            mock_service.list_positions = AsyncMock(return_value=[sample_position])

            response = client.get("/positions")

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["instrument"] == "EUR_USD"

    def test_list_positions_with_filters(self, client, sample_position):
        """Should filter positions by status and instrument."""
        with patch("tradingsystem.api.positions.position_service") as mock_service:
            mock_service.list_positions = AsyncMock(return_value=[sample_position])

            response = client.get(
                "/positions",
                params={"status": "OPEN", "instrument": "EUR_USD", "limit": 25},
            )

            assert response.status_code == 200
            mock_service.list_positions.assert_called_once_with(
                status=PositionStatus.OPEN,
                instrument="EUR_USD",
                strategy_id=None,
                limit=25,
                offset=0,
            )

    def test_list_positions_empty(self, client):
        """Should return empty list when no positions."""
        with patch("tradingsystem.api.positions.position_service") as mock_service:
            mock_service.list_positions = AsyncMock(return_value=[])

            response = client.get("/positions")

            assert response.status_code == 200
            assert response.json() == []


class TestGetOpenPositions:
    """Tests for GET /positions/open."""

    def test_get_open_positions(self, client, sample_position):
        """Should return open positions."""
        with patch("tradingsystem.api.positions.position_service") as mock_service:
            mock_service.get_open_positions = AsyncMock(return_value=[sample_position])

            response = client.get("/positions/open")

            assert response.status_code == 200
            assert len(response.json()) == 1

    def test_get_open_positions_with_instrument(self, client):
        """Should filter by instrument."""
        with patch("tradingsystem.api.positions.position_service") as mock_service:
            mock_service.get_open_positions = AsyncMock(return_value=[])

            response = client.get("/positions/open", params={"instrument": "GBP_USD"})

            assert response.status_code == 200
            mock_service.get_open_positions.assert_called_once_with("GBP_USD")


class TestGetPositionSummary:
    """Tests for GET /positions/summary."""

    def test_get_position_summary(self, client):
        """Should return position summary."""
        summary = PositionSummary(
            total_positions=3,
            open_positions=2,
            closed_positions=1,
            total_pnl=Decimal("150.00"),
            unrealized_pnl=Decimal("50.00"),
            realized_pnl=Decimal("100.00"),
            winning_trades=2,
            losing_trades=1,
            win_rate=Decimal("0.67"),
        )

        with patch("tradingsystem.api.positions.position_service") as mock_service:
            mock_service.get_position_summary = AsyncMock(return_value=summary)

            response = client.get("/positions/summary")

            assert response.status_code == 200
            data = response.json()
            assert data["total_positions"] == 3
            assert data["open_positions"] == 2


class TestGetPosition:
    """Tests for GET /positions/{position_id}."""

    def test_get_position_found(self, client, sample_position):
        """Should return position when found."""
        with patch("tradingsystem.api.positions.position_service") as mock_service:
            mock_service.get_position = AsyncMock(return_value=sample_position)

            response = client.get(f"/positions/{sample_position.id}")

            assert response.status_code == 200
            assert response.json()["id"] == str(sample_position.id)

    def test_get_position_not_found(self, client):
        """Should return 404 when position not found."""
        with patch("tradingsystem.api.positions.position_service") as mock_service:
            mock_service.get_position = AsyncMock(return_value=None)

            response = client.get(f"/positions/{uuid4()}")

            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()


class TestClosePosition:
    """Tests for POST /positions/{position_id}/close."""

    def test_close_position_success(self, client, closed_position):
        """Should close position at specified price."""
        with patch("tradingsystem.api.positions.position_service") as mock_service:
            mock_service.close_position = AsyncMock(return_value=closed_position)

            response = client.post(
                f"/positions/{closed_position.id}/close",
                json={"exit_price": "1.0900"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "CLOSED"
            assert data["pnl"] == "50.00"

    def test_close_position_already_closed(self, client):
        """Should return 400 when position already closed."""
        with patch("tradingsystem.api.positions.position_service") as mock_service:
            mock_service.close_position = AsyncMock(
                side_effect=ValueError("Position already closed")
            )

            response = client.post(
                f"/positions/{uuid4()}/close",
                json={"exit_price": "1.0900"},
            )

            assert response.status_code == 400
            assert "already closed" in response.json()["detail"].lower()


class TestClosePositionAtMarket:
    """Tests for POST /positions/{position_id}/close-at-market."""

    def test_close_at_market_success(self, client, closed_position, sample_order):
        """Should close position at market price."""
        with patch("tradingsystem.api.positions.paper_trading_service") as mock_service:
            mock_service.close_trade = AsyncMock(
                return_value=(sample_order, closed_position)
            )

            response = client.post(f"/positions/{closed_position.id}/close-at-market")

            assert response.status_code == 200
            data = response.json()
            assert "position" in data
            assert "order_id" in data
            assert "P&L" in data["message"]

    def test_close_at_market_not_found(self, client):
        """Should return 400 when position not found."""
        with patch("tradingsystem.api.positions.paper_trading_service") as mock_service:
            mock_service.close_trade = AsyncMock(
                side_effect=ValueError("Position not found")
            )

            response = client.post(f"/positions/{uuid4()}/close-at-market")

            assert response.status_code == 400


class TestGetPositionPnl:
    """Tests for GET /positions/{position_id}/pnl."""

    def test_get_pnl_closed_position(self, client, closed_position):
        """Should return realized P&L for closed position."""
        with patch("tradingsystem.api.positions.position_service") as mock_service:
            mock_service.get_position = AsyncMock(return_value=closed_position)

            response = client.get(f"/positions/{closed_position.id}/pnl")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "CLOSED"
            assert data["pnl"] == "50.00"

    def test_get_pnl_open_position(self, client, sample_position):
        """Should return unrealized P&L for open position."""
        with patch("tradingsystem.api.positions.position_service") as mock_service:
            mock_service.get_position = AsyncMock(return_value=sample_position)
            mock_service.calculate_unrealized_pnl = AsyncMock(
                return_value=Decimal("25.00")
            )

            response = client.get(f"/positions/{sample_position.id}/pnl")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "OPEN"
            assert "unrealized_pnl" in data

    def test_get_pnl_not_found(self, client):
        """Should return 404 when position not found."""
        with patch("tradingsystem.api.positions.position_service") as mock_service:
            mock_service.get_position = AsyncMock(return_value=None)

            response = client.get(f"/positions/{uuid4()}/pnl")

            assert response.status_code == 404


class TestGetAccountSummary:
    """Tests for GET /positions/account/summary."""

    def test_get_account_summary(self, client):
        """Should return paper trading account summary."""
        account_data = {
            "balance": "10000.00",
            "equity": "10050.00",
            "unrealized_pnl": "50.00",
            "margin_used": "500.00",
            "open_positions": 2,
        }

        with patch("tradingsystem.api.positions.paper_trading_service") as mock_service:
            mock_service.get_account_summary = AsyncMock(return_value=account_data)

            response = client.get("/positions/account/summary")

            assert response.status_code == 200
            data = response.json()
            assert data["balance"] == "10000.00"


class TestGetMarketPrice:
    """Tests for GET /positions/market/price/{instrument}."""

    def test_get_market_price_success(self, client):
        """Should return current market price."""
        price_data = {
            "instrument": "EUR_USD",
            "bid": "1.0850",
            "ask": "1.0852",
            "time": datetime.now(timezone.utc).isoformat(),
        }

        with patch("tradingsystem.api.positions.paper_trading_service") as mock_service:
            mock_service.get_current_price = AsyncMock(return_value=price_data)

            response = client.get("/positions/market/price/EUR_USD")

            assert response.status_code == 200
            data = response.json()
            assert data["instrument"] == "EUR_USD"
            assert "bid" in data
            assert "ask" in data

    def test_get_market_price_invalid_instrument(self, client):
        """Should return 400 for invalid instrument."""
        with patch("tradingsystem.api.positions.paper_trading_service") as mock_service:
            mock_service.get_current_price = AsyncMock(
                side_effect=Exception("Unknown instrument")
            )

            response = client.get("/positions/market/price/INVALID")

            assert response.status_code == 400
