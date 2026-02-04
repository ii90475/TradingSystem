"""Tests for paper trading service."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from tradingsystem.models.order import OrderSide, OrderStatus, OrderType, TradingMode
from tradingsystem.models.position import PositionSide, PositionStatus
from tradingsystem.services import paper_trading_service


# --- Fixtures ---


@pytest.fixture
def mock_order():
    """Create mock filled order."""
    order = MagicMock()
    order.id = uuid4()
    order.instrument = "EUR_USD"
    order.side = OrderSide.BUY
    order.order_type = OrderType.MARKET
    order.quantity = Decimal("10000")
    order.status = OrderStatus.FILLED
    order.filled_quantity = Decimal("10000")
    order.filled_price = Decimal("1.0850")
    return order


@pytest.fixture
def mock_position():
    """Create mock open position."""
    position = MagicMock()
    position.id = uuid4()
    position.instrument = "EUR_USD"
    position.side = PositionSide.LONG
    position.quantity = Decimal("10000")
    position.entry_price = Decimal("1.0850")
    position.status = PositionStatus.OPEN
    position.strategy_id = "test_strategy"
    position.pnl = Decimal("0")
    return position


@pytest.fixture
def mock_closed_position():
    """Create mock closed position."""
    position = MagicMock()
    position.id = uuid4()
    position.instrument = "EUR_USD"
    position.side = PositionSide.LONG
    position.quantity = Decimal("10000")
    position.entry_price = Decimal("1.0850")
    position.status = PositionStatus.CLOSED
    position.exit_price = Decimal("1.0900")
    position.pnl = Decimal("50.00")
    position.strategy_id = "test_strategy"
    return position


# --- execute_trade Tests ---


class TestExecuteTrade:
    """Tests for execute_trade function."""

    @pytest.mark.asyncio
    async def test_creates_order_and_position(self, mock_order, mock_position):
        """Should create order and open position."""
        with patch.object(paper_trading_service, "order_service") as mock_order_svc, \
             patch.object(paper_trading_service, "position_service") as mock_pos_svc:
            mock_order_svc.create_order = AsyncMock(return_value=mock_order)
            mock_pos_svc.open_position = AsyncMock(return_value=mock_position)

            order, position = await paper_trading_service.execute_trade(
                instrument="EUR_USD",
                side=OrderSide.BUY,
                quantity=Decimal("10000"),
                strategy_id="test_strategy",
            )

            assert order.status == OrderStatus.FILLED
            assert position.side == PositionSide.LONG
            mock_order_svc.create_order.assert_called_once()
            mock_pos_svc.open_position.assert_called_once()

    @pytest.mark.asyncio
    async def test_creates_short_position_for_sell(self, mock_order, mock_position):
        """Should create SHORT position for SELL order."""
        mock_order.side = OrderSide.SELL
        mock_position.side = PositionSide.SHORT

        with patch.object(paper_trading_service, "order_service") as mock_order_svc, \
             patch.object(paper_trading_service, "position_service") as mock_pos_svc:
            mock_order_svc.create_order = AsyncMock(return_value=mock_order)
            mock_pos_svc.open_position = AsyncMock(return_value=mock_position)

            order, position = await paper_trading_service.execute_trade(
                instrument="EUR_USD",
                side=OrderSide.SELL,
                quantity=Decimal("10000"),
            )

            # Check position was created with SHORT side
            call_args = mock_pos_svc.open_position.call_args[0][0]
            assert call_args.side == PositionSide.SHORT

    @pytest.mark.asyncio
    async def test_raises_when_order_not_filled(self, mock_order):
        """Should raise RuntimeError when order not filled."""
        mock_order.status = OrderStatus.PENDING

        with patch.object(paper_trading_service, "order_service") as mock_order_svc:
            mock_order_svc.create_order = AsyncMock(return_value=mock_order)

            with pytest.raises(RuntimeError, match="not filled"):
                await paper_trading_service.execute_trade(
                    instrument="EUR_USD",
                    side=OrderSide.BUY,
                    quantity=Decimal("10000"),
                )

    @pytest.mark.asyncio
    async def test_uses_paper_mode(self, mock_order, mock_position):
        """Should create order with PAPER trading mode."""
        with patch.object(paper_trading_service, "order_service") as mock_order_svc, \
             patch.object(paper_trading_service, "position_service") as mock_pos_svc:
            mock_order_svc.create_order = AsyncMock(return_value=mock_order)
            mock_pos_svc.open_position = AsyncMock(return_value=mock_position)

            await paper_trading_service.execute_trade(
                instrument="EUR_USD",
                side=OrderSide.BUY,
                quantity=Decimal("10000"),
            )

            call_args = mock_order_svc.create_order.call_args[0][0]
            assert call_args.mode == TradingMode.PAPER


# --- close_trade Tests ---


class TestCloseTrade:
    """Tests for close_trade function."""

    @pytest.mark.asyncio
    async def test_closes_position(self, mock_order, mock_position):
        """Should close position with closing order."""
        mock_order.side = OrderSide.SELL
        closed_position = MagicMock()
        closed_position.status = PositionStatus.CLOSED
        closed_position.pnl = Decimal("50.00")

        with patch.object(paper_trading_service, "order_service") as mock_order_svc, \
             patch.object(paper_trading_service, "position_service") as mock_pos_svc:
            mock_pos_svc.get_position = AsyncMock(return_value=mock_position)
            mock_order_svc.create_order = AsyncMock(return_value=mock_order)
            mock_pos_svc.close_position = AsyncMock(return_value=closed_position)

            order, position = await paper_trading_service.close_trade(mock_position.id)

            assert position.status == PositionStatus.CLOSED
            mock_pos_svc.close_position.assert_called_once()

    @pytest.mark.asyncio
    async def test_creates_opposite_side_order(self, mock_order, mock_position):
        """Should create SELL order to close LONG position."""
        mock_order.side = OrderSide.SELL
        closed_position = MagicMock()
        closed_position.status = PositionStatus.CLOSED

        with patch.object(paper_trading_service, "order_service") as mock_order_svc, \
             patch.object(paper_trading_service, "position_service") as mock_pos_svc:
            mock_pos_svc.get_position = AsyncMock(return_value=mock_position)
            mock_order_svc.create_order = AsyncMock(return_value=mock_order)
            mock_pos_svc.close_position = AsyncMock(return_value=closed_position)

            await paper_trading_service.close_trade(mock_position.id)

            call_args = mock_order_svc.create_order.call_args[0][0]
            assert call_args.side == OrderSide.SELL

    @pytest.mark.asyncio
    async def test_creates_buy_order_for_short(self, mock_order, mock_position):
        """Should create BUY order to close SHORT position."""
        mock_position.side = PositionSide.SHORT
        mock_order.side = OrderSide.BUY
        closed_position = MagicMock()
        closed_position.status = PositionStatus.CLOSED

        with patch.object(paper_trading_service, "order_service") as mock_order_svc, \
             patch.object(paper_trading_service, "position_service") as mock_pos_svc:
            mock_pos_svc.get_position = AsyncMock(return_value=mock_position)
            mock_order_svc.create_order = AsyncMock(return_value=mock_order)
            mock_pos_svc.close_position = AsyncMock(return_value=closed_position)

            await paper_trading_service.close_trade(mock_position.id)

            call_args = mock_order_svc.create_order.call_args[0][0]
            assert call_args.side == OrderSide.BUY

    @pytest.mark.asyncio
    async def test_raises_for_nonexistent_position(self):
        """Should raise ValueError for non-existent position."""
        with patch.object(paper_trading_service, "position_service") as mock_pos_svc:
            mock_pos_svc.get_position = AsyncMock(return_value=None)

            with pytest.raises(ValueError, match="Position not found"):
                await paper_trading_service.close_trade(uuid4())

    @pytest.mark.asyncio
    async def test_raises_for_non_open_position(self, mock_closed_position):
        """Should raise ValueError for non-open position."""
        with patch.object(paper_trading_service, "position_service") as mock_pos_svc:
            mock_pos_svc.get_position = AsyncMock(return_value=mock_closed_position)

            with pytest.raises(ValueError, match="not open"):
                await paper_trading_service.close_trade(mock_closed_position.id)

    @pytest.mark.asyncio
    async def test_raises_when_closing_order_not_filled(self, mock_order, mock_position):
        """Should raise RuntimeError when closing order not filled."""
        mock_order.status = OrderStatus.REJECTED

        with patch.object(paper_trading_service, "order_service") as mock_order_svc, \
             patch.object(paper_trading_service, "position_service") as mock_pos_svc:
            mock_pos_svc.get_position = AsyncMock(return_value=mock_position)
            mock_order_svc.create_order = AsyncMock(return_value=mock_order)

            with pytest.raises(RuntimeError, match="not filled"):
                await paper_trading_service.close_trade(mock_position.id)


# --- get_account_summary Tests ---


class TestGetAccountSummary:
    """Tests for get_account_summary function."""

    @pytest.mark.asyncio
    async def test_returns_summary(self):
        """Should return account summary dict."""
        mock_summary = MagicMock()
        mock_summary.total_positions = 10
        mock_summary.open_positions = 3
        mock_summary.closed_positions = 7
        mock_summary.total_pnl = Decimal("1500.00")
        mock_summary.realized_pnl = Decimal("1200.00")
        mock_summary.unrealized_pnl = Decimal("300.00")

        with patch.object(paper_trading_service, "order_service") as mock_order_svc, \
             patch.object(paper_trading_service, "position_service") as mock_pos_svc:
            mock_pos_svc.get_position_summary = AsyncMock(return_value=mock_summary)
            mock_order_svc.count_orders = AsyncMock(return_value=2)

            result = await paper_trading_service.get_account_summary()

            assert result["mode"] == "PAPER"
            assert result["positions"]["total"] == 10
            assert result["positions"]["open"] == 3
            assert result["positions"]["closed"] == 7
            assert result["pending_orders"] == 2
            assert result["pnl"]["total"] == "1500.00"
            assert result["pnl"]["realized"] == "1200.00"
            assert result["pnl"]["unrealized"] == "300.00"

    @pytest.mark.asyncio
    async def test_counts_pending_orders(self):
        """Should count pending orders."""
        mock_summary = MagicMock()
        mock_summary.total_positions = 0
        mock_summary.open_positions = 0
        mock_summary.closed_positions = 0
        mock_summary.total_pnl = Decimal("0")
        mock_summary.realized_pnl = Decimal("0")
        mock_summary.unrealized_pnl = Decimal("0")

        with patch.object(paper_trading_service, "order_service") as mock_order_svc, \
             patch.object(paper_trading_service, "position_service") as mock_pos_svc:
            mock_pos_svc.get_position_summary = AsyncMock(return_value=mock_summary)
            mock_order_svc.count_orders = AsyncMock(return_value=5)

            result = await paper_trading_service.get_account_summary()

            mock_order_svc.count_orders.assert_called_once_with(OrderStatus.PENDING)
            assert result["pending_orders"] == 5


# --- get_current_price Tests ---


class TestGetCurrentPrice:
    """Tests for get_current_price function."""

    @pytest.mark.asyncio
    async def test_returns_price_info(self):
        """Should return bid/ask/spread info."""
        mock_rate = MagicMock()
        mock_rate.bid = Decimal("1.0850")
        mock_rate.ask = Decimal("1.0852")
        mock_rate.time = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)
        mock_rate.tradeable = True

        with patch.object(paper_trading_service, "rateservice_client") as mock_client:
            mock_client.get_current_rate = AsyncMock(return_value=mock_rate)

            result = await paper_trading_service.get_current_price("EUR_USD")

            assert result["instrument"] == "EUR_USD"
            assert result["bid"] == "1.0850"
            assert result["ask"] == "1.0852"
            assert result["spread"] == "0.0002"
            assert result["tradeable"] is True

    @pytest.mark.asyncio
    async def test_calculates_spread(self):
        """Should calculate spread from bid/ask."""
        mock_rate = MagicMock()
        mock_rate.bid = Decimal("1.0000")
        mock_rate.ask = Decimal("1.0010")
        mock_rate.time = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)
        mock_rate.tradeable = True

        with patch.object(paper_trading_service, "rateservice_client") as mock_client:
            mock_client.get_current_rate = AsyncMock(return_value=mock_rate)

            result = await paper_trading_service.get_current_price("GBP_USD")

            assert result["spread"] == "0.0010"

    @pytest.mark.asyncio
    async def test_includes_time_iso_format(self):
        """Should include time in ISO format."""
        mock_rate = MagicMock()
        mock_rate.bid = Decimal("1.0850")
        mock_rate.ask = Decimal("1.0852")
        mock_rate.time = datetime(2024, 1, 15, 12, 30, 45, tzinfo=timezone.utc)
        mock_rate.tradeable = True

        with patch.object(paper_trading_service, "rateservice_client") as mock_client:
            mock_client.get_current_rate = AsyncMock(return_value=mock_rate)

            result = await paper_trading_service.get_current_price("EUR_USD")

            assert "2024-01-15" in result["time"]
            assert "12:30:45" in result["time"]
