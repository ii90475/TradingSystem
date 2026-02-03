"""Pytest configuration and shared fixtures for TradingSystem tests."""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio

from tradingsystem.core.rateservice import CurrentRate
from tradingsystem.core.oanda_trading import OandaAccount, OandaOrderResponse, OandaTrade
from tradingsystem.models.order import Order, OrderSide, OrderStatus, OrderType
from tradingsystem.models.position import Position, PositionSide, PositionStatus


# ============================================================================
# Event Loop Configuration
# ============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ============================================================================
# Mock Data Factories
# ============================================================================

@pytest.fixture
def mock_current_rate():
    """Factory for creating mock CurrentRate objects."""
    def _create(
        pair: str = "EUR_USD",
        bid: Decimal = Decimal("1.0850"),
        ask: Decimal = Decimal("1.0852"),
    ) -> CurrentRate:
        return CurrentRate(
            pair=pair,
            bid=bid,
            ask=ask,
            time=datetime.now(timezone.utc),
            tradeable=True,
        )
    return _create


@pytest.fixture
def mock_oanda_account():
    """Factory for creating mock OandaAccount objects."""
    def _create(
        balance: Decimal = Decimal("10000.00"),
        nav: Decimal = Decimal("10050.00"),
        unrealized_pnl: Decimal = Decimal("50.00"),
        margin_used: Decimal = Decimal("500.00"),
        margin_available: Decimal = Decimal("9500.00"),
        open_trade_count: int = 2,
    ) -> OandaAccount:
        return OandaAccount(
            id="001-001-12345-001",
            balance=balance,
            nav=nav,
            unrealized_pnl=unrealized_pnl,
            margin_used=margin_used,
            margin_available=margin_available,
            open_trade_count=open_trade_count,
            open_position_count=open_trade_count,
        )
    return _create


@pytest.fixture
def mock_oanda_order_response():
    """Factory for creating mock OandaOrderResponse objects."""
    def _create(
        instrument: str = "EUR_USD",
        units: Decimal = Decimal("1000"),
        price: Decimal = Decimal("1.0850"),
        state: str = "FILLED",
    ) -> OandaOrderResponse:
        return OandaOrderResponse(
            order_id=f"order-{uuid4().hex[:8]}",
            trade_id=f"trade-{uuid4().hex[:8]}",
            instrument=instrument,
            units=units,
            price=price,
            time=datetime.now(timezone.utc),
            state=state,
        )
    return _create


@pytest.fixture
def mock_oanda_trade():
    """Factory for creating mock OandaTrade objects."""
    def _create(
        instrument: str = "EUR_USD",
        units: Decimal = Decimal("1000"),
        price: Decimal = Decimal("1.0850"),
        unrealized_pnl: Decimal = Decimal("25.00"),
    ) -> OandaTrade:
        return OandaTrade(
            id=f"trade-{uuid4().hex[:8]}",
            instrument=instrument,
            units=units,
            price=price,
            unrealized_pnl=unrealized_pnl,
            state="OPEN",
            open_time=datetime.now(timezone.utc),
        )
    return _create


@pytest.fixture
def mock_order():
    """Factory for creating mock Order objects."""
    def _create(
        instrument: str = "EUR_USD",
        side: OrderSide = OrderSide.BUY,
        order_type: OrderType = OrderType.MARKET,
        quantity: Decimal = Decimal("1000"),
        status: OrderStatus = OrderStatus.PENDING,
        filled_price: Decimal | None = None,
    ) -> Order:
        return Order(
            id=uuid4(),
            external_id=None,
            strategy_id="test_strategy",
            instrument=instrument,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=None,
            status=status,
            created_at=datetime.now(timezone.utc),
            filled_at=datetime.now(timezone.utc) if filled_price else None,
            filled_price=filled_price,
            filled_quantity=quantity if filled_price else None,
        )
    return _create


@pytest.fixture
def mock_position():
    """Factory for creating mock Position objects."""
    def _create(
        instrument: str = "EUR_USD",
        side: PositionSide = PositionSide.LONG,
        quantity: Decimal = Decimal("1000"),
        entry_price: Decimal = Decimal("1.0850"),
        status: PositionStatus = PositionStatus.OPEN,
        exit_price: Decimal | None = None,
        pnl: Decimal | None = None,
    ) -> Position:
        return Position(
            id=uuid4(),
            instrument=instrument,
            side=side,
            quantity=quantity,
            entry_price=entry_price,
            entry_time=datetime.now(timezone.utc),
            exit_price=exit_price,
            exit_time=datetime.now(timezone.utc) if exit_price else None,
            status=status,
            strategy_id="test_strategy",
            pnl=pnl,
            pnl_percent=None,
        )
    return _create


# ============================================================================
# Mock Clients
# ============================================================================

@pytest.fixture
def mock_rateservice_client(mock_current_rate):
    """Mock RateService client."""
    client = AsyncMock()
    client.get_current_rate = AsyncMock(return_value=mock_current_rate())
    client.get_current_rates = AsyncMock(return_value=[mock_current_rate()])
    client.check_health = AsyncMock(return_value={"healthy": True, "status": "healthy"})
    return client


@pytest.fixture
def mock_oanda_client(mock_oanda_account, mock_oanda_order_response, mock_oanda_trade):
    """Mock OANDA trading client."""
    client = AsyncMock()
    client.get_account_summary = AsyncMock(return_value=mock_oanda_account())
    client.get_open_trades = AsyncMock(return_value=[mock_oanda_trade()])
    client.create_market_order = AsyncMock(return_value=mock_oanda_order_response())
    client.close_trade = AsyncMock(return_value=mock_oanda_order_response())
    client.close_all_trades = AsyncMock(return_value=[mock_oanda_order_response()])
    client.check_connectivity = AsyncMock(return_value={"connected": True})
    return client


# ============================================================================
# Database Mocking
# ============================================================================

class MockCursor:
    """Mock async database cursor."""

    def __init__(self, results: list[dict] | None = None):
        self.results = results or []
        self.result_index = 0
        self.executed_queries: list[tuple] = []
        self.connection = AsyncMock()
        self.connection.commit = AsyncMock()

    async def execute(self, query: str, params: tuple = None):
        self.executed_queries.append((query, params))

    async def fetchone(self) -> dict | None:
        if self.result_index < len(self.results):
            result = self.results[self.result_index]
            self.result_index += 1
            return result
        return None

    async def fetchall(self) -> list[dict]:
        return self.results

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class MockConnection:
    """Mock async database connection."""

    def __init__(self, cursor: MockCursor):
        self._cursor = cursor

    def cursor(self, row_factory=None):
        return self._cursor

    async def commit(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


@pytest.fixture
def mock_db_cursor():
    """Factory for creating mock database cursors with predefined results."""
    def _create(results: list[dict] | None = None) -> MockCursor:
        return MockCursor(results)
    return _create


@pytest.fixture
def mock_get_cursor(mock_db_cursor):
    """Mock the get_cursor context manager."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _mock_get_cursor(results: list[dict] | None = None):
        cursor = mock_db_cursor(results)
        yield cursor

    return _mock_get_cursor


# ============================================================================
# Settings Override Fixtures
# ============================================================================

@pytest.fixture
def settings_live_trading_enabled():
    """Override settings to enable live trading."""
    with patch("tradingsystem.core.config.settings") as mock_settings:
        mock_settings.live_trading_enabled = True
        mock_settings.paper_trading_enabled = False
        mock_settings.max_position_size_pct = 5.0
        mock_settings.max_daily_loss_pct = 2.0
        mock_settings.max_open_positions = 5
        mock_settings.oanda_api_key = "test-api-key"
        mock_settings.oanda_account_id = "test-account-id"
        yield mock_settings


@pytest.fixture
def settings_live_trading_disabled():
    """Override settings to disable live trading."""
    with patch("tradingsystem.core.config.settings") as mock_settings:
        mock_settings.live_trading_enabled = False
        mock_settings.paper_trading_enabled = True
        mock_settings.max_position_size_pct = 5.0
        mock_settings.max_daily_loss_pct = 2.0
        mock_settings.max_open_positions = 5
        yield mock_settings


# ============================================================================
# Test Helpers
# ============================================================================

@pytest.fixture
def assert_decimal_equal():
    """Helper to compare Decimal values with tolerance."""
    def _assert(actual: Decimal, expected: Decimal, tolerance: Decimal = Decimal("0.0001")):
        assert abs(actual - expected) < tolerance, f"Expected {expected}, got {actual}"
    return _assert
