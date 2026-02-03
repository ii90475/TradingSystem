"""Unit tests for the Order Service."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

import pytest

from tradingsystem.models.order import (
    Order,
    OrderCreate,
    OrderSide,
    OrderStatus,
    OrderType,
    TradingMode,
)
from tradingsystem.services import order_service


class TestCreateOrder:
    """Tests for order_service.create_order()."""

    @pytest.fixture
    def order_create_request(self):
        """Create a basic order request."""
        return OrderCreate(
            instrument="EUR_USD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("1000"),
            strategy_id="test_strategy",
            mode=TradingMode.LIVE,
        )

    @pytest.fixture
    def mock_db_row(self):
        """Create a mock database row for order."""
        return {
            "id": uuid4(),
            "external_id": None,
            "strategy_id": "test_strategy",
            "instrument": "EUR_USD",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": Decimal("1000"),
            "price": None,
            "status": "PENDING",
            "created_at": datetime.now(timezone.utc),
            "filled_at": None,
            "filled_price": None,
            "filled_quantity": None,
        }

    @pytest.mark.asyncio
    async def test_create_order_live_mode(self, order_create_request, mock_db_row, mock_get_cursor):
        """Creating an order in LIVE mode should not auto-fill."""
        with patch("tradingsystem.services.order_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.fetchone = AsyncMock(return_value=mock_db_row)
            cursor.connection = MagicMock()
            cursor.connection.commit = AsyncMock()

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            order = await order_service.create_order(order_create_request)

            assert order.status == OrderStatus.PENDING
            assert order.instrument == "EUR_USD"
            assert order.side == OrderSide.BUY
            assert order.quantity == Decimal("1000")

    @pytest.mark.asyncio
    async def test_create_order_paper_market_auto_fills(self, mock_db_row, mock_current_rate):
        """Creating a MARKET order in PAPER mode should auto-fill."""
        paper_request = OrderCreate(
            instrument="EUR_USD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("1000"),
            mode=TradingMode.PAPER,
        )

        filled_row = mock_db_row.copy()
        filled_row["status"] = "FILLED"
        filled_row["filled_price"] = Decimal("1.0852")
        filled_row["filled_quantity"] = Decimal("1000")
        filled_row["filled_at"] = datetime.now(timezone.utc)

        with patch("tradingsystem.services.order_service.get_cursor") as mock_cursor_ctx, \
             patch("tradingsystem.services.order_service.rateservice_client") as mock_rateservice:

            cursor = MagicMock()
            cursor.execute = AsyncMock()
            # First call returns pending, second call returns filled
            cursor.fetchone = AsyncMock(side_effect=[mock_db_row, mock_db_row, filled_row])
            cursor.connection = MagicMock()
            cursor.connection.commit = AsyncMock()

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            mock_rateservice.get_current_rate = AsyncMock(return_value=mock_current_rate())

            order = await order_service.create_order(paper_request)

            assert order.status == OrderStatus.FILLED
            assert order.filled_price is not None

    @pytest.mark.asyncio
    async def test_create_order_paper_limit_stays_pending(self, mock_db_row):
        """Creating a LIMIT order in PAPER mode should stay pending."""
        limit_request = OrderCreate(
            instrument="EUR_USD",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("1000"),
            price=Decimal("1.0800"),
            mode=TradingMode.PAPER,
        )

        with patch("tradingsystem.services.order_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.fetchone = AsyncMock(return_value=mock_db_row)
            cursor.connection = MagicMock()
            cursor.connection.commit = AsyncMock()

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            order = await order_service.create_order(limit_request)

            # LIMIT orders don't auto-fill
            assert order.status == OrderStatus.PENDING


class TestFillOrderAtMarket:
    """Tests for order_service.fill_order_at_market()."""

    @pytest.fixture
    def pending_order_row(self):
        """Create a pending order database row."""
        return {
            "id": uuid4(),
            "external_id": None,
            "strategy_id": "test_strategy",
            "instrument": "EUR_USD",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": Decimal("1000"),
            "price": None,
            "status": "PENDING",
            "created_at": datetime.now(timezone.utc),
            "filled_at": None,
            "filled_price": None,
            "filled_quantity": None,
        }

    @pytest.mark.asyncio
    async def test_fill_buy_order_uses_ask_price(self, pending_order_row, mock_current_rate):
        """BUY orders should fill at the ask price (plus slippage)."""
        order_id = pending_order_row["id"]
        rate = mock_current_rate(bid=Decimal("1.0850"), ask=Decimal("1.0852"))

        filled_row = pending_order_row.copy()
        filled_row["status"] = "FILLED"
        filled_row["filled_at"] = datetime.now(timezone.utc)

        with patch("tradingsystem.services.order_service.get_cursor") as mock_cursor_ctx, \
             patch("tradingsystem.services.order_service.rateservice_client") as mock_rateservice:

            cursor = MagicMock()
            cursor.execute = AsyncMock()

            # Capture the fill price from the UPDATE call
            fill_prices = []

            async def capture_execute(query, params=None):
                if params and "FILLED" in str(params):
                    # This is the fill_order UPDATE call
                    fill_prices.append(params[2])  # filled_price is 3rd param

            cursor.execute = AsyncMock(side_effect=capture_execute)
            cursor.fetchone = AsyncMock(side_effect=[pending_order_row, filled_row])
            cursor.connection = MagicMock()
            cursor.connection.commit = AsyncMock()

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            mock_rateservice.get_current_rate = AsyncMock(return_value=rate)

            await order_service.fill_order_at_market(order_id)

            # Verify fill price is ask + slippage
            assert len(fill_prices) == 1
            expected_price = rate.ask + (rate.ask * Decimal("0.0005"))
            assert fill_prices[0] == expected_price

    @pytest.mark.asyncio
    async def test_fill_sell_order_uses_bid_price(self, mock_current_rate):
        """SELL orders should fill at the bid price (minus slippage)."""
        order_id = uuid4()
        sell_order_row = {
            "id": order_id,
            "external_id": None,
            "strategy_id": "test_strategy",
            "instrument": "EUR_USD",
            "side": "SELL",
            "order_type": "MARKET",
            "quantity": Decimal("1000"),
            "price": None,
            "status": "PENDING",
            "created_at": datetime.now(timezone.utc),
            "filled_at": None,
            "filled_price": None,
            "filled_quantity": None,
        }

        rate = mock_current_rate(bid=Decimal("1.0850"), ask=Decimal("1.0852"))

        filled_row = sell_order_row.copy()
        filled_row["status"] = "FILLED"
        filled_row["filled_at"] = datetime.now(timezone.utc)

        with patch("tradingsystem.services.order_service.get_cursor") as mock_cursor_ctx, \
             patch("tradingsystem.services.order_service.rateservice_client") as mock_rateservice:

            cursor = MagicMock()
            fill_prices = []

            async def capture_execute(query, params=None):
                if params and "FILLED" in str(params):
                    fill_prices.append(params[2])

            cursor.execute = AsyncMock(side_effect=capture_execute)
            cursor.fetchone = AsyncMock(side_effect=[sell_order_row, filled_row])
            cursor.connection = MagicMock()
            cursor.connection.commit = AsyncMock()

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            mock_rateservice.get_current_rate = AsyncMock(return_value=rate)

            await order_service.fill_order_at_market(order_id)

            # Verify fill price is bid - slippage
            assert len(fill_prices) == 1
            expected_price = rate.bid - (rate.bid * Decimal("0.0005"))
            assert fill_prices[0] == expected_price

    @pytest.mark.asyncio
    async def test_fill_order_not_found_raises_error(self):
        """Filling a non-existent order should raise ValueError."""
        order_id = uuid4()

        with patch("tradingsystem.services.order_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.fetchone = AsyncMock(return_value=None)

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            with pytest.raises(ValueError, match="Order not found"):
                await order_service.fill_order_at_market(order_id)

    @pytest.mark.asyncio
    async def test_fill_already_filled_order_raises_error(self):
        """Filling an already-filled order should raise ValueError."""
        order_id = uuid4()
        filled_order_row = {
            "id": order_id,
            "external_id": None,
            "strategy_id": "test_strategy",
            "instrument": "EUR_USD",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": Decimal("1000"),
            "price": None,
            "status": "FILLED",  # Already filled
            "created_at": datetime.now(timezone.utc),
            "filled_at": datetime.now(timezone.utc),
            "filled_price": Decimal("1.0850"),
            "filled_quantity": Decimal("1000"),
        }

        with patch("tradingsystem.services.order_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.fetchone = AsyncMock(return_value=filled_order_row)

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            with pytest.raises(ValueError, match="Order is not pending"):
                await order_service.fill_order_at_market(order_id)


class TestFillOrder:
    """Tests for order_service.fill_order()."""

    @pytest.mark.asyncio
    async def test_fill_order_success(self):
        """fill_order should update status and fill details."""
        order_id = uuid4()
        fill_price = Decimal("1.0855")
        fill_quantity = Decimal("1000")

        filled_row = {
            "id": order_id,
            "external_id": None,
            "strategy_id": "test_strategy",
            "instrument": "EUR_USD",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": Decimal("1000"),
            "price": None,
            "status": "FILLED",
            "created_at": datetime.now(timezone.utc),
            "filled_at": datetime.now(timezone.utc),
            "filled_price": fill_price,
            "filled_quantity": fill_quantity,
        }

        with patch("tradingsystem.services.order_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.fetchone = AsyncMock(return_value=filled_row)
            cursor.connection = MagicMock()
            cursor.connection.commit = AsyncMock()

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            order = await order_service.fill_order(order_id, fill_price, fill_quantity)

            assert order.status == OrderStatus.FILLED
            assert order.filled_price == fill_price
            assert order.filled_quantity == fill_quantity

    @pytest.mark.asyncio
    async def test_fill_order_not_found(self):
        """fill_order should raise error for non-existent order.

        Note: The fill_order function raises ValueError when the UPDATE returns None
        (order doesn't exist or was already modified).
        """
        from contextlib import asynccontextmanager

        order_id = uuid4()

        cursor = MagicMock()
        cursor.execute = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=None)
        cursor.connection = MagicMock()
        cursor.connection.commit = AsyncMock()

        @asynccontextmanager
        async def mock_get_cursor():
            yield cursor

        with patch("tradingsystem.services.order_service.get_cursor", mock_get_cursor):
            with pytest.raises(ValueError, match="Order not found"):
                await order_service.fill_order(order_id, Decimal("1.0850"), Decimal("1000"))


class TestCancelOrder:
    """Tests for order_service.cancel_order()."""

    @pytest.mark.asyncio
    async def test_cancel_pending_order_success(self):
        """Cancelling a pending order should update status to CANCELLED."""
        order_id = uuid4()
        cancelled_row = {
            "id": order_id,
            "external_id": None,
            "strategy_id": "test_strategy",
            "instrument": "EUR_USD",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": Decimal("1000"),
            "price": Decimal("1.0800"),
            "status": "CANCELLED",
            "created_at": datetime.now(timezone.utc),
            "filled_at": None,
            "filled_price": None,
            "filled_quantity": None,
        }

        with patch("tradingsystem.services.order_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.fetchone = AsyncMock(return_value=cancelled_row)
            cursor.connection = MagicMock()
            cursor.connection.commit = AsyncMock()

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            order = await order_service.cancel_order(order_id)

            assert order.status == OrderStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_filled_order_raises_error(self):
        """Cancelling a filled order should raise ValueError."""
        from contextlib import asynccontextmanager

        order_id = uuid4()

        cursor = MagicMock()
        cursor.execute = AsyncMock()
        # UPDATE with WHERE status = PENDING returns None for filled order
        cursor.fetchone = AsyncMock(return_value=None)
        cursor.connection = MagicMock()
        cursor.connection.commit = AsyncMock()

        @asynccontextmanager
        async def mock_get_cursor():
            yield cursor

        with patch("tradingsystem.services.order_service.get_cursor", mock_get_cursor):
            with pytest.raises(ValueError, match="Order not found or not pending"):
                await order_service.cancel_order(order_id)


class TestGetOrder:
    """Tests for order_service.get_order()."""

    @pytest.mark.asyncio
    async def test_get_order_exists(self):
        """get_order should return order when found."""
        order_id = uuid4()
        order_row = {
            "id": order_id,
            "external_id": "ext-123",
            "strategy_id": "test_strategy",
            "instrument": "EUR_USD",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": Decimal("1000"),
            "price": None,
            "status": "FILLED",
            "created_at": datetime.now(timezone.utc),
            "filled_at": datetime.now(timezone.utc),
            "filled_price": Decimal("1.0850"),
            "filled_quantity": Decimal("1000"),
        }

        with patch("tradingsystem.services.order_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.fetchone = AsyncMock(return_value=order_row)

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            order = await order_service.get_order(order_id)

            assert order is not None
            assert order.id == order_id
            assert order.external_id == "ext-123"

    @pytest.mark.asyncio
    async def test_get_order_not_found(self):
        """get_order should return None when order not found."""
        order_id = uuid4()

        with patch("tradingsystem.services.order_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.fetchone = AsyncMock(return_value=None)

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            order = await order_service.get_order(order_id)

            assert order is None


class TestListOrders:
    """Tests for order_service.list_orders()."""

    @pytest.mark.asyncio
    async def test_list_orders_no_filter(self):
        """list_orders should return all orders without filters."""
        order_rows = [
            {
                "id": uuid4(),
                "external_id": None,
                "strategy_id": "strategy1",
                "instrument": "EUR_USD",
                "side": "BUY",
                "order_type": "MARKET",
                "quantity": Decimal("1000"),
                "price": None,
                "status": "FILLED",
                "created_at": datetime.now(timezone.utc),
                "filled_at": datetime.now(timezone.utc),
                "filled_price": Decimal("1.0850"),
                "filled_quantity": Decimal("1000"),
            },
            {
                "id": uuid4(),
                "external_id": None,
                "strategy_id": "strategy2",
                "instrument": "GBP_USD",
                "side": "SELL",
                "order_type": "LIMIT",
                "quantity": Decimal("500"),
                "price": Decimal("1.2700"),
                "status": "PENDING",
                "created_at": datetime.now(timezone.utc),
                "filled_at": None,
                "filled_price": None,
                "filled_quantity": None,
            },
        ]

        with patch("tradingsystem.services.order_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.fetchall = AsyncMock(return_value=order_rows)

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            orders = await order_service.list_orders()

            assert len(orders) == 2
            assert orders[0].instrument == "EUR_USD"
            assert orders[1].instrument == "GBP_USD"

    @pytest.mark.asyncio
    async def test_list_orders_with_status_filter(self):
        """list_orders should filter by status."""
        pending_row = {
            "id": uuid4(),
            "external_id": None,
            "strategy_id": "strategy1",
            "instrument": "EUR_USD",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": Decimal("1000"),
            "price": Decimal("1.0800"),
            "status": "PENDING",
            "created_at": datetime.now(timezone.utc),
            "filled_at": None,
            "filled_price": None,
            "filled_quantity": None,
        }

        with patch("tradingsystem.services.order_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            executed_queries = []

            async def capture_execute(query, params=None):
                executed_queries.append((query, params))

            cursor.execute = AsyncMock(side_effect=capture_execute)
            cursor.fetchall = AsyncMock(return_value=[pending_row])

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            orders = await order_service.list_orders(status=OrderStatus.PENDING)

            assert len(orders) == 1
            assert orders[0].status == OrderStatus.PENDING
            # Verify status filter was applied
            assert any("PENDING" in str(q[1]) for q in executed_queries)


class TestCountOrders:
    """Tests for order_service.count_orders()."""

    @pytest.mark.asyncio
    async def test_count_all_orders(self):
        """count_orders should return total count without filter."""
        with patch("tradingsystem.services.order_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.fetchone = AsyncMock(return_value={"count": 42})

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            count = await order_service.count_orders()

            assert count == 42

    @pytest.mark.asyncio
    async def test_count_orders_with_status(self):
        """count_orders should filter by status."""
        with patch("tradingsystem.services.order_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.fetchone = AsyncMock(return_value={"count": 5})

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            count = await order_service.count_orders(status=OrderStatus.PENDING)

            assert count == 5
