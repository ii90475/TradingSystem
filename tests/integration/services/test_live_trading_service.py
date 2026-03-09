"""Integration tests for the Live Trading Service.

These tests verify the interaction between live trading, risk management,
order service, position service, and the OANDA API.
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

import pytest

from tradingsystem.models.order import OrderSide, OrderStatus, OrderType, TradingMode
from tradingsystem.models.position import PositionSide, PositionStatus
from tradingsystem.services import live_trading_service
from tradingsystem.services.live_trading_service import LiveTradingError
from tradingsystem.services.risk_manager import RiskCheckResult, RiskViolation


class TestExecuteLiveTrade:
    """Tests for live_trading_service.execute_live_trade()."""

    @pytest.fixture
    def mock_order_row(self):
        """Create a mock order database row."""
        def _create(status="PENDING", order_id=None):
            return {
                "id": order_id or uuid4(),
                "external_id": None,
                "strategy_id": "test_strategy",
                "instrument": "EUR_USD",
                "side": "BUY",
                "order_type": "MARKET",
                "quantity": Decimal("1000"),
                "price": None,
                "status": status,
                "created_at": datetime.now(timezone.utc),
                "filled_at": datetime.now(timezone.utc) if status == "FILLED" else None,
                "filled_price": Decimal("1.0850") if status == "FILLED" else None,
                "filled_quantity": Decimal("1000") if status == "FILLED" else None,
            }
        return _create

    @pytest.fixture
    def mock_position_row(self):
        """Create a mock position database row."""
        return {
            "id": uuid4(),
            "instrument": "EUR_USD",
            "side": "LONG",
            "quantity": Decimal("1000"),
            "entry_price": Decimal("1.0850"),
            "entry_time": datetime.now(timezone.utc),
            "exit_price": None,
            "exit_time": None,
            "status": "OPEN",
            "strategy_id": "test_strategy",
            "pnl": None,
            "pnl_percent": None,
        }

    @pytest.mark.asyncio
    async def test_execute_live_trade_success(
        self, mock_order_row, mock_position_row, mock_oanda_order_response
    ):
        """Successful live trade should create order, execute via OANDA, create position."""
        order_id = uuid4()
        pending_row = mock_order_row("PENDING", order_id)
        filled_row = mock_order_row("FILLED", order_id)
        oanda_response = mock_oanda_order_response(
            instrument="EUR_USD",
            units=Decimal("1000"),
            price=Decimal("1.0850"),
        )

        with patch("tradingsystem.services.live_trading_service.risk_manager") as mock_risk, \
             patch("tradingsystem.services.live_trading_service.order_service") as mock_orders, \
             patch("tradingsystem.services.live_trading_service.position_service") as mock_positions, \
             patch("tradingsystem.services.live_trading_service.oanda_trading_client") as mock_oanda, \
             patch("tradingsystem.services.live_trading_service.get_cursor") as mock_cursor_ctx:

            # Set trading mode
            mock_oanda.trading_mode = "PAPER"

            # Risk check passes
            mock_risk.check_trade = AsyncMock(return_value=RiskCheckResult(approved=True))

            # Order service creates and fills order
            mock_order = MagicMock()
            mock_order.id = order_id
            mock_order.status = OrderStatus.PENDING
            mock_orders.create_order = AsyncMock(return_value=mock_order)

            filled_order = MagicMock()
            filled_order.id = order_id
            filled_order.status = OrderStatus.FILLED
            mock_orders.fill_order = AsyncMock(return_value=filled_order)

            # OANDA executes trade
            mock_oanda.create_market_order = AsyncMock(return_value=oanda_response)

            # Position service creates position
            mock_position = MagicMock()
            mock_position.id = uuid4()
            mock_position.status = PositionStatus.OPEN
            mock_positions.open_position = AsyncMock(return_value=mock_position)

            # Mock database cursor for external ID updates
            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.connection = MagicMock()
            cursor.connection.commit = AsyncMock()
            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            order, position, response = await live_trading_service.execute_live_trade(
                instrument="EUR_USD",
                side=OrderSide.BUY,
                quantity=Decimal("1000"),
                strategy_id="test_strategy",
            )

            # Verify risk check was called
            mock_risk.check_trade.assert_called_once_with(
                "EUR_USD", OrderSide.BUY, Decimal("1000")
            )

            # Verify order was created
            mock_orders.create_order.assert_called_once()

            # Verify OANDA was called with correct units (positive for BUY)
            mock_oanda.create_market_order.assert_called_once()
            call_args = mock_oanda.create_market_order.call_args
            assert call_args.kwargs["instrument"] == "EUR_USD"
            assert call_args.kwargs["units"] == Decimal("1000")

            # Verify position was created
            mock_positions.open_position.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_live_trade_risk_rejected(self):
        """Trade rejected by risk manager should raise LiveTradingError."""
        with patch("tradingsystem.services.live_trading_service.risk_manager") as mock_risk:
            mock_risk.check_trade = AsyncMock(return_value=RiskCheckResult(
                approved=False,
                violations=[RiskViolation.MAX_POSITION_SIZE],
                messages=["Position too large"],
            ))

            with pytest.raises(LiveTradingError, match="rejected by risk manager"):
                await live_trading_service.execute_live_trade(
                    instrument="EUR_USD",
                    side=OrderSide.BUY,
                    quantity=Decimal("100000"),
                )

    @pytest.mark.asyncio
    async def test_execute_live_trade_oanda_failure_marks_order_failed(self):
        """OANDA failure should mark local order as rejected."""
        order_id = uuid4()

        with patch("tradingsystem.services.live_trading_service.risk_manager") as mock_risk, \
             patch("tradingsystem.services.live_trading_service.order_service") as mock_orders, \
             patch("tradingsystem.services.live_trading_service.oanda_trading_client") as mock_oanda, \
             patch("tradingsystem.services.live_trading_service.get_cursor") as mock_cursor_ctx:

            mock_oanda.trading_mode = "PAPER"
            mock_risk.check_trade = AsyncMock(return_value=RiskCheckResult(approved=True))

            mock_order = MagicMock()
            mock_order.id = order_id
            mock_orders.create_order = AsyncMock(return_value=mock_order)

            # OANDA fails
            mock_oanda.create_market_order = AsyncMock(
                side_effect=Exception("OANDA API error")
            )

            # Mock cursor for marking order failed
            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.connection = MagicMock()
            cursor.connection.commit = AsyncMock()
            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            with pytest.raises(LiveTradingError, match="Oanda execution failed"):
                await live_trading_service.execute_live_trade(
                    instrument="EUR_USD",
                    side=OrderSide.BUY,
                    quantity=Decimal("1000"),
                )

            # Verify order was marked as failed (REJECTED status)
            assert cursor.execute.called
            execute_calls = cursor.execute.call_args_list
            assert any("REJECTED" in str(call) for call in execute_calls)

    @pytest.mark.asyncio
    async def test_execute_sell_trade_uses_negative_units(self, mock_oanda_order_response):
        """SELL trades should use negative units for OANDA."""
        order_id = uuid4()
        oanda_response = mock_oanda_order_response(units=Decimal("-1000"))

        with patch("tradingsystem.services.live_trading_service.risk_manager") as mock_risk, \
             patch("tradingsystem.services.live_trading_service.order_service") as mock_orders, \
             patch("tradingsystem.services.live_trading_service.position_service") as mock_positions, \
             patch("tradingsystem.services.live_trading_service.oanda_trading_client") as mock_oanda, \
             patch("tradingsystem.services.live_trading_service.get_cursor") as mock_cursor_ctx:

            mock_oanda.trading_mode = "PAPER"
            mock_risk.check_trade = AsyncMock(return_value=RiskCheckResult(approved=True))

            mock_order = MagicMock()
            mock_order.id = order_id
            mock_orders.create_order = AsyncMock(return_value=mock_order)

            filled_order = MagicMock()
            filled_order.id = order_id
            mock_orders.fill_order = AsyncMock(return_value=filled_order)

            mock_oanda.create_market_order = AsyncMock(return_value=oanda_response)

            mock_position = MagicMock()
            mock_position.id = uuid4()
            mock_positions.open_position = AsyncMock(return_value=mock_position)

            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.connection = MagicMock()
            cursor.connection.commit = AsyncMock()
            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            await live_trading_service.execute_live_trade(
                instrument="EUR_USD",
                side=OrderSide.SELL,
                quantity=Decimal("1000"),
            )

            # Verify OANDA was called with negative units for SELL
            call_args = mock_oanda.create_market_order.call_args
            assert call_args.kwargs["units"] == Decimal("-1000")


class TestCloseLiveTrade:
    """Tests for live_trading_service.close_live_trade()."""

    @pytest.fixture
    def open_position(self, mock_position):
        """Create an open position."""
        return mock_position(
            side=PositionSide.LONG,
            status=PositionStatus.OPEN,
            quantity=Decimal("1000"),
            entry_price=Decimal("1.0850"),
        )

    @pytest.mark.asyncio
    async def test_close_live_trade_success(self, open_position, mock_oanda_order_response):
        """Successful close should update position and record P&L."""
        position_id = open_position.id
        oanda_response = mock_oanda_order_response(price=Decimal("1.0900"))

        with patch("tradingsystem.services.live_trading_service.position_service") as mock_positions, \
             patch("tradingsystem.services.live_trading_service.order_service") as mock_orders, \
             patch("tradingsystem.services.live_trading_service.oanda_trading_client") as mock_oanda, \
             patch("tradingsystem.services.live_trading_service.risk_manager") as mock_risk, \
             patch("tradingsystem.services.live_trading_service.get_cursor") as mock_cursor_ctx:

            mock_oanda.trading_mode = "PAPER"
            mock_positions.get_position = AsyncMock(return_value=open_position)

            mock_order = MagicMock()
            mock_order.id = uuid4()
            mock_orders.create_order = AsyncMock(return_value=mock_order)

            filled_order = MagicMock()
            filled_order.id = mock_order.id
            mock_orders.fill_order = AsyncMock(return_value=filled_order)

            mock_oanda.close_trade = AsyncMock(return_value=oanda_response)

            closed_position = MagicMock()
            closed_position.id = position_id
            closed_position.pnl = Decimal("5.00")  # Profit
            mock_positions.close_position = AsyncMock(return_value=closed_position)

            # Mock cursor for external ID lookup
            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.fetchone = AsyncMock(return_value={"strategy_id": "test:oanda-trade-123"})
            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            order, position, response = await live_trading_service.close_live_trade(
                position_id=position_id,
                oanda_trade_id="oanda-trade-123",
            )

            # Verify trade was closed
            mock_oanda.close_trade.assert_called_once_with("oanda-trade-123")

            # Verify P&L was recorded for risk tracking
            mock_risk.record_trade_result.assert_called_once_with(Decimal("5.00"))

    @pytest.mark.asyncio
    async def test_close_live_trade_position_not_found(self):
        """Closing non-existent position should raise error."""
        position_id = uuid4()

        with patch("tradingsystem.services.live_trading_service.position_service") as mock_positions:
            mock_positions.get_position = AsyncMock(return_value=None)

            with pytest.raises(LiveTradingError, match="Position not found"):
                await live_trading_service.close_live_trade(position_id)

    @pytest.mark.asyncio
    async def test_close_live_trade_position_not_open(self, mock_position):
        """Closing already-closed position should raise error."""
        closed_position = mock_position(status=PositionStatus.CLOSED)

        with patch("tradingsystem.services.live_trading_service.position_service") as mock_positions:
            mock_positions.get_position = AsyncMock(return_value=closed_position)

            with pytest.raises(LiveTradingError, match="Position is not open"):
                await live_trading_service.close_live_trade(closed_position.id)

    @pytest.mark.asyncio
    async def test_close_live_trade_no_oanda_id(self, open_position):
        """Closing without OANDA trade ID when none stored should raise error."""
        position_id = open_position.id

        with patch("tradingsystem.services.live_trading_service.position_service") as mock_positions, \
             patch("tradingsystem.services.live_trading_service.get_cursor") as mock_cursor_ctx:

            mock_positions.get_position = AsyncMock(return_value=open_position)

            # No OANDA trade ID found
            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.fetchone = AsyncMock(return_value={"strategy_id": None})
            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            with pytest.raises(LiveTradingError, match="No Oanda trade ID"):
                await live_trading_service.close_live_trade(position_id)

    @pytest.mark.asyncio
    async def test_close_live_trade_records_loss(self, open_position, mock_oanda_order_response):
        """Closing at loss should record negative P&L for risk tracking."""
        position_id = open_position.id
        oanda_response = mock_oanda_order_response(price=Decimal("1.0800"))  # Lower than entry

        with patch("tradingsystem.services.live_trading_service.position_service") as mock_positions, \
             patch("tradingsystem.services.live_trading_service.order_service") as mock_orders, \
             patch("tradingsystem.services.live_trading_service.oanda_trading_client") as mock_oanda, \
             patch("tradingsystem.services.live_trading_service.risk_manager") as mock_risk, \
             patch("tradingsystem.services.live_trading_service.get_cursor") as mock_cursor_ctx:

            mock_oanda.trading_mode = "PAPER"
            mock_positions.get_position = AsyncMock(return_value=open_position)

            mock_order = MagicMock()
            mock_order.id = uuid4()
            mock_orders.create_order = AsyncMock(return_value=mock_order)
            mock_orders.fill_order = AsyncMock(return_value=mock_order)

            mock_oanda.close_trade = AsyncMock(return_value=oanda_response)

            closed_position = MagicMock()
            closed_position.pnl = Decimal("-5.00")  # Loss
            mock_positions.close_position = AsyncMock(return_value=closed_position)

            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.fetchone = AsyncMock(return_value={"strategy_id": "test:trade-123"})
            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            await live_trading_service.close_live_trade(
                position_id=position_id,
                oanda_trade_id="trade-123",
            )

            # Verify loss was recorded
            mock_risk.record_trade_result.assert_called_once_with(Decimal("-5.00"))


class TestEmergencyCloseAll:
    """Tests for live_trading_service.emergency_close_all()."""

    @pytest.mark.asyncio
    async def test_emergency_close_disabled(self):
        """Emergency close should fail if live trading is disabled."""
        with patch("tradingsystem.services.live_trading_service.settings") as mock_settings:
            mock_settings.live_trading_enabled = False

            with pytest.raises(LiveTradingError, match="Live trading is not enabled"):
                await live_trading_service.emergency_close_all()

    @pytest.mark.asyncio
    async def test_emergency_close_success(self, mock_oanda_order_response):
        """Emergency close should close all open OANDA trades."""
        close_responses = [
            mock_oanda_order_response(instrument="EUR_USD"),
            mock_oanda_order_response(instrument="GBP_USD"),
        ]

        with patch("tradingsystem.services.live_trading_service.settings") as mock_settings, \
             patch("tradingsystem.services.live_trading_service.oanda_trading_client") as mock_oanda:

            mock_settings.live_trading_enabled = True
            mock_oanda.close_all_trades = AsyncMock(return_value=close_responses)

            results = await live_trading_service.emergency_close_all()

            assert len(results) == 2
            assert results[0]["instrument"] == "EUR_USD"
            assert results[1]["instrument"] == "GBP_USD"
            assert all(r["status"] == "closed" for r in results)

    @pytest.mark.asyncio
    async def test_emergency_close_oanda_failure(self):
        """Emergency close should raise error if OANDA fails."""
        with patch("tradingsystem.services.live_trading_service.settings") as mock_settings, \
             patch("tradingsystem.services.live_trading_service.oanda_trading_client") as mock_oanda:

            mock_settings.live_trading_enabled = True
            mock_oanda.close_all_trades = AsyncMock(
                side_effect=Exception("OANDA emergency close failed")
            )

            with pytest.raises(LiveTradingError, match="Emergency close failed"):
                await live_trading_service.emergency_close_all()


class TestGetLiveAccountStatus:
    """Tests for live_trading_service.get_live_account_status()."""

    @pytest.mark.asyncio
    async def test_account_status_connected(self, mock_oanda_account):
        """Should return full status when OANDA is connected."""
        account = mock_oanda_account(
            balance=Decimal("10000.00"),
            nav=Decimal("10050.00"),
            unrealized_pnl=Decimal("50.00"),
        )

        with patch("tradingsystem.services.live_trading_service.settings") as mock_settings, \
             patch("tradingsystem.services.live_trading_service.oanda_trading_client") as mock_oanda, \
             patch("tradingsystem.services.live_trading_service.risk_manager") as mock_risk:

            mock_settings.live_trading_enabled = True
            mock_oanda.trading_mode = "LIVE"
            mock_oanda.check_connectivity = AsyncMock(return_value={"connected": True})
            mock_oanda.get_account_summary = AsyncMock(return_value=account)
            mock_risk.get_risk_status = MagicMock(return_value={
                "consecutive_losses": 0,
                "circuit_breaker_active": False,
            })

            status = await live_trading_service.get_live_account_status()

            assert status["mode"] == "LIVE"
            assert status["oanda"]["connected"] is True
            assert status["account"]["balance"] == "10000.00"
            assert status["account"]["nav"] == "10050.00"

    @pytest.mark.asyncio
    async def test_account_status_disconnected(self):
        """Should return limited status when OANDA is disconnected."""
        with patch("tradingsystem.services.live_trading_service.settings") as mock_settings, \
             patch("tradingsystem.services.live_trading_service.oanda_trading_client") as mock_oanda, \
             patch("tradingsystem.services.live_trading_service.risk_manager") as mock_risk:

            mock_settings.live_trading_enabled = False
            mock_oanda.trading_mode = "PAPER"
            mock_oanda.check_connectivity = AsyncMock(return_value={
                "connected": False,
                "error": "Connection timeout",
            })
            mock_risk.get_risk_status = MagicMock(return_value={})

            status = await live_trading_service.get_live_account_status()

            assert status["mode"] == "PAPER"
            assert status["oanda"]["connected"] is False
            assert status["account"] is None

    @pytest.mark.asyncio
    async def test_account_status_exception_handling(self):
        """Should handle exceptions gracefully."""
        with patch("tradingsystem.services.live_trading_service.settings") as mock_settings, \
             patch("tradingsystem.services.live_trading_service.oanda_trading_client") as mock_oanda, \
             patch("tradingsystem.services.live_trading_service.risk_manager") as mock_risk:

            mock_settings.live_trading_enabled = True
            mock_oanda.check_connectivity = AsyncMock(side_effect=Exception("Network error"))
            mock_risk.get_risk_status = MagicMock(return_value={})

            status = await live_trading_service.get_live_account_status()

            assert status["mode"] == "PAPER"
            assert "error" in status
            assert status["oanda"]["connected"] is False
