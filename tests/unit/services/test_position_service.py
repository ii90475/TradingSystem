"""Unit tests for the Position Service."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

import pytest

from tradingsystem.models.position import (
    Position,
    PositionCreate,
    PositionSide,
    PositionStatus,
    PositionSummary,
)
from tradingsystem.services import position_service


class TestOpenPosition:
    """Tests for position_service.open_position()."""

    @pytest.fixture
    def position_create_request(self):
        """Create a basic position request."""
        return PositionCreate(
            instrument="EUR_USD",
            side=PositionSide.LONG,
            quantity=Decimal("1000"),
            entry_price=Decimal("1.0850"),
            strategy_id="test_strategy",
        )

    @pytest.fixture
    def mock_position_row(self):
        """Create a mock database row for position."""
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
    async def test_open_position_creates_open_position(
        self, position_create_request, mock_position_row
    ):
        """open_position should create a position with OPEN status."""
        with patch("tradingsystem.services.position_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.fetchone = AsyncMock(return_value=mock_position_row)
            cursor.connection = MagicMock()
            cursor.connection.commit = AsyncMock()

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            position = await position_service.open_position(position_create_request)

            assert position.status == PositionStatus.OPEN
            assert position.instrument == "EUR_USD"
            assert position.side == PositionSide.LONG
            assert position.quantity == Decimal("1000")
            assert position.entry_price == Decimal("1.0850")
            assert position.exit_price is None
            assert position.pnl is None

    @pytest.mark.asyncio
    async def test_open_short_position(self, mock_position_row):
        """open_position should handle SHORT positions."""
        short_request = PositionCreate(
            instrument="GBP_USD",
            side=PositionSide.SHORT,
            quantity=Decimal("500"),
            entry_price=Decimal("1.2700"),
        )

        short_row = mock_position_row.copy()
        short_row["instrument"] = "GBP_USD"
        short_row["side"] = "SHORT"
        short_row["quantity"] = Decimal("500")
        short_row["entry_price"] = Decimal("1.2700")

        with patch("tradingsystem.services.position_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.fetchone = AsyncMock(return_value=short_row)
            cursor.connection = MagicMock()
            cursor.connection.commit = AsyncMock()

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            position = await position_service.open_position(short_request)

            assert position.side == PositionSide.SHORT
            assert position.instrument == "GBP_USD"


class TestClosePosition:
    """Tests for position_service.close_position()."""

    @pytest.fixture
    def open_long_position_row(self):
        """Create an open LONG position row."""
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

    @pytest.fixture
    def open_short_position_row(self):
        """Create an open SHORT position row."""
        return {
            "id": uuid4(),
            "instrument": "EUR_USD",
            "side": "SHORT",
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
    async def test_close_long_position_profit(self, open_long_position_row):
        """Closing LONG at higher price should show profit."""
        position_id = open_long_position_row["id"]
        exit_price = Decimal("1.0900")  # Higher than entry 1.0850

        # Expected P&L: (1.0900 - 1.0850) * 1000 = 5.00
        expected_pnl = Decimal("5.00")

        closed_row = open_long_position_row.copy()
        closed_row["status"] = "CLOSED"
        closed_row["exit_price"] = exit_price
        closed_row["exit_time"] = datetime.now(timezone.utc)
        closed_row["pnl"] = expected_pnl

        with patch("tradingsystem.services.position_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            cursor.execute = AsyncMock()
            # First call: get_position, second call: UPDATE
            cursor.fetchone = AsyncMock(side_effect=[open_long_position_row, closed_row])
            cursor.connection = MagicMock()
            cursor.connection.commit = AsyncMock()

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            position = await position_service.close_position(position_id, exit_price)

            assert position.status == PositionStatus.CLOSED
            assert position.exit_price == exit_price
            assert position.pnl == expected_pnl

    @pytest.mark.asyncio
    async def test_close_long_position_loss(self, open_long_position_row):
        """Closing LONG at lower price should show loss."""
        position_id = open_long_position_row["id"]
        exit_price = Decimal("1.0800")  # Lower than entry 1.0850

        # Expected P&L: (1.0800 - 1.0850) * 1000 = -5.00
        expected_pnl = Decimal("-5.00")

        closed_row = open_long_position_row.copy()
        closed_row["status"] = "CLOSED"
        closed_row["exit_price"] = exit_price
        closed_row["pnl"] = expected_pnl

        with patch("tradingsystem.services.position_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.fetchone = AsyncMock(side_effect=[open_long_position_row, closed_row])
            cursor.connection = MagicMock()
            cursor.connection.commit = AsyncMock()

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            position = await position_service.close_position(position_id, exit_price)

            assert position.pnl == expected_pnl

    @pytest.mark.asyncio
    async def test_close_short_position_profit(self, open_short_position_row):
        """Closing SHORT at lower price should show profit."""
        position_id = open_short_position_row["id"]
        exit_price = Decimal("1.0800")  # Lower than entry 1.0850

        # Expected P&L: (1.0850 - 1.0800) * 1000 = 5.00
        expected_pnl = Decimal("5.00")

        closed_row = open_short_position_row.copy()
        closed_row["status"] = "CLOSED"
        closed_row["exit_price"] = exit_price
        closed_row["pnl"] = expected_pnl

        with patch("tradingsystem.services.position_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.fetchone = AsyncMock(side_effect=[open_short_position_row, closed_row])
            cursor.connection = MagicMock()
            cursor.connection.commit = AsyncMock()

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            position = await position_service.close_position(position_id, exit_price)

            assert position.pnl == expected_pnl

    @pytest.mark.asyncio
    async def test_close_short_position_loss(self, open_short_position_row):
        """Closing SHORT at higher price should show loss."""
        position_id = open_short_position_row["id"]
        exit_price = Decimal("1.0900")  # Higher than entry 1.0850

        # Expected P&L: (1.0850 - 1.0900) * 1000 = -5.00
        expected_pnl = Decimal("-5.00")

        closed_row = open_short_position_row.copy()
        closed_row["status"] = "CLOSED"
        closed_row["exit_price"] = exit_price
        closed_row["pnl"] = expected_pnl

        with patch("tradingsystem.services.position_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.fetchone = AsyncMock(side_effect=[open_short_position_row, closed_row])
            cursor.connection = MagicMock()
            cursor.connection.commit = AsyncMock()

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            position = await position_service.close_position(position_id, exit_price)

            assert position.pnl == expected_pnl

    @pytest.mark.asyncio
    async def test_close_position_not_found(self):
        """Closing a non-existent position should raise ValueError."""
        position_id = uuid4()

        with patch("tradingsystem.services.position_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.fetchone = AsyncMock(return_value=None)

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            with pytest.raises(ValueError, match="Position not found"):
                await position_service.close_position(position_id, Decimal("1.0900"))

    @pytest.mark.asyncio
    async def test_close_already_closed_position(self):
        """Closing an already-closed position should raise ValueError."""
        position_id = uuid4()
        closed_row = {
            "id": position_id,
            "instrument": "EUR_USD",
            "side": "LONG",
            "quantity": Decimal("1000"),
            "entry_price": Decimal("1.0850"),
            "entry_time": datetime.now(timezone.utc),
            "exit_price": Decimal("1.0900"),
            "exit_time": datetime.now(timezone.utc),
            "status": "CLOSED",
            "strategy_id": "test_strategy",
            "pnl": Decimal("5.00"),
            "pnl_percent": Decimal("0.46"),
        }

        with patch("tradingsystem.services.position_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.fetchone = AsyncMock(return_value=closed_row)

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            with pytest.raises(ValueError, match="Position is not open"):
                await position_service.close_position(position_id, Decimal("1.0950"))


class TestClosePositionAtMarket:
    """Tests for position_service.close_position_at_market()."""

    @pytest.fixture
    def open_long_row(self):
        """Create an open LONG position row."""
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
    async def test_close_long_at_market_uses_bid(self, open_long_row, mock_current_rate):
        """Closing LONG at market should use bid price (selling)."""
        position_id = open_long_row["id"]
        rate = mock_current_rate(bid=Decimal("1.0900"), ask=Decimal("1.0902"))

        # Expected exit price = bid - slippage
        expected_exit = rate.bid - (rate.bid * Decimal("0.0005"))

        closed_row = open_long_row.copy()
        closed_row["status"] = "CLOSED"
        closed_row["exit_price"] = expected_exit

        with patch("tradingsystem.services.position_service.get_cursor") as mock_cursor_ctx, \
             patch("tradingsystem.services.position_service.rateservice_client") as mock_rateservice:

            cursor = MagicMock()
            exit_prices = []

            async def capture_execute(query, params=None):
                if params and len(params) > 0 and isinstance(params[0], Decimal):
                    exit_prices.append(params[0])

            cursor.execute = AsyncMock(side_effect=capture_execute)
            cursor.fetchone = AsyncMock(side_effect=[open_long_row, open_long_row, closed_row])
            cursor.connection = MagicMock()
            cursor.connection.commit = AsyncMock()

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            mock_rateservice.get_current_rate = AsyncMock(return_value=rate)

            await position_service.close_position_at_market(position_id)

            # Verify bid price was used (with slippage subtracted for LONG)
            assert len(exit_prices) == 1
            assert exit_prices[0] == expected_exit

    @pytest.mark.asyncio
    async def test_close_short_at_market_uses_ask(self, mock_current_rate):
        """Closing SHORT at market should use ask price (buying to cover)."""
        open_short_row = {
            "id": uuid4(),
            "instrument": "EUR_USD",
            "side": "SHORT",
            "quantity": Decimal("1000"),
            "entry_price": Decimal("1.0900"),
            "entry_time": datetime.now(timezone.utc),
            "exit_price": None,
            "exit_time": None,
            "status": "OPEN",
            "strategy_id": "test_strategy",
            "pnl": None,
            "pnl_percent": None,
        }

        rate = mock_current_rate(bid=Decimal("1.0850"), ask=Decimal("1.0852"))

        # Expected exit price = ask + slippage (buying back)
        expected_exit = rate.ask + (rate.ask * Decimal("0.0005"))

        closed_row = open_short_row.copy()
        closed_row["status"] = "CLOSED"
        closed_row["exit_price"] = expected_exit

        with patch("tradingsystem.services.position_service.get_cursor") as mock_cursor_ctx, \
             patch("tradingsystem.services.position_service.rateservice_client") as mock_rateservice:

            cursor = MagicMock()
            exit_prices = []

            async def capture_execute(query, params=None):
                if params and len(params) > 0 and isinstance(params[0], Decimal):
                    exit_prices.append(params[0])

            cursor.execute = AsyncMock(side_effect=capture_execute)
            cursor.fetchone = AsyncMock(side_effect=[open_short_row, open_short_row, closed_row])
            cursor.connection = MagicMock()
            cursor.connection.commit = AsyncMock()

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            mock_rateservice.get_current_rate = AsyncMock(return_value=rate)

            await position_service.close_position_at_market(open_short_row["id"])

            # Verify ask price was used (with slippage added for SHORT)
            assert len(exit_prices) == 1
            assert exit_prices[0] == expected_exit


class TestGetPosition:
    """Tests for position_service.get_position()."""

    @pytest.mark.asyncio
    async def test_get_position_exists(self):
        """get_position should return position when found."""
        position_id = uuid4()
        position_row = {
            "id": position_id,
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

        with patch("tradingsystem.services.position_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.fetchone = AsyncMock(return_value=position_row)

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            position = await position_service.get_position(position_id)

            assert position is not None
            assert position.id == position_id
            assert position.instrument == "EUR_USD"

    @pytest.mark.asyncio
    async def test_get_position_not_found(self):
        """get_position should return None when not found."""
        position_id = uuid4()

        with patch("tradingsystem.services.position_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.fetchone = AsyncMock(return_value=None)

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            position = await position_service.get_position(position_id)

            assert position is None


class TestListPositions:
    """Tests for position_service.list_positions()."""

    @pytest.mark.asyncio
    async def test_list_positions_no_filter(self):
        """list_positions should return all positions without filters."""
        position_rows = [
            {
                "id": uuid4(),
                "instrument": "EUR_USD",
                "side": "LONG",
                "quantity": Decimal("1000"),
                "entry_price": Decimal("1.0850"),
                "entry_time": datetime.now(timezone.utc),
                "exit_price": None,
                "exit_time": None,
                "status": "OPEN",
                "strategy_id": "strategy1",
                "pnl": None,
                "pnl_percent": None,
            },
            {
                "id": uuid4(),
                "instrument": "GBP_USD",
                "side": "SHORT",
                "quantity": Decimal("500"),
                "entry_price": Decimal("1.2700"),
                "entry_time": datetime.now(timezone.utc),
                "exit_price": Decimal("1.2650"),
                "exit_time": datetime.now(timezone.utc),
                "status": "CLOSED",
                "strategy_id": "strategy2",
                "pnl": Decimal("25.00"),
                "pnl_percent": Decimal("3.94"),
            },
        ]

        with patch("tradingsystem.services.position_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.fetchall = AsyncMock(return_value=position_rows)

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            positions = await position_service.list_positions()

            assert len(positions) == 2

    @pytest.mark.asyncio
    async def test_list_positions_with_status_filter(self):
        """list_positions should filter by status."""
        open_row = {
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

        with patch("tradingsystem.services.position_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            executed_queries = []

            async def capture_execute(query, params=None):
                executed_queries.append((query, params))

            cursor.execute = AsyncMock(side_effect=capture_execute)
            cursor.fetchall = AsyncMock(return_value=[open_row])

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            positions = await position_service.list_positions(status=PositionStatus.OPEN)

            assert len(positions) == 1
            assert positions[0].status == PositionStatus.OPEN


class TestGetPositionSummary:
    """Tests for position_service.get_position_summary()."""

    @pytest.mark.asyncio
    async def test_position_summary_calculation(self, mock_current_rate):
        """get_position_summary should aggregate position data correctly."""
        summary_row = {
            "total_positions": 10,
            "open_positions": 3,
            "closed_positions": 7,
            "realized_pnl": Decimal("150.00"),
        }

        open_positions = [
            {
                "id": uuid4(),
                "instrument": "EUR_USD",
                "side": "LONG",
                "quantity": Decimal("1000"),
                "entry_price": Decimal("1.0850"),
                "entry_time": datetime.now(timezone.utc),
                "exit_price": None,
                "exit_time": None,
                "status": "OPEN",
                "strategy_id": "test",
                "pnl": None,
                "pnl_percent": None,
            },
        ]

        rate = mock_current_rate(bid=Decimal("1.0900"), ask=Decimal("1.0902"))

        with patch("tradingsystem.services.position_service.get_cursor") as mock_cursor_ctx, \
             patch("tradingsystem.services.position_service.rateservice_client") as mock_rateservice:

            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.fetchone = AsyncMock(return_value=summary_row)
            cursor.fetchall = AsyncMock(return_value=open_positions)

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            mock_rateservice.get_current_rate = AsyncMock(return_value=rate)

            summary = await position_service.get_position_summary()

            assert summary.total_positions == 10
            assert summary.open_positions == 3
            assert summary.closed_positions == 7
            assert summary.realized_pnl == Decimal("150.00")

    @pytest.mark.asyncio
    async def test_position_summary_no_positions(self):
        """get_position_summary should handle empty portfolio."""
        summary_row = {
            "total_positions": 0,
            "open_positions": 0,
            "closed_positions": 0,
            "realized_pnl": Decimal("0"),
        }

        with patch("tradingsystem.services.position_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.fetchone = AsyncMock(return_value=summary_row)

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            summary = await position_service.get_position_summary()

            assert summary.total_positions == 0
            assert summary.unrealized_pnl == Decimal("0")


class TestCalculateUnrealizedPnl:
    """Tests for position_service.calculate_unrealized_pnl()."""

    @pytest.mark.asyncio
    async def test_unrealized_pnl_long_profit(self, mock_current_rate, mock_position):
        """Calculate unrealized P&L for LONG position in profit."""
        position = mock_position(
            side=PositionSide.LONG,
            entry_price=Decimal("1.0850"),
            quantity=Decimal("1000"),
            status=PositionStatus.OPEN,
        )

        # Current bid is 1.0900 (higher than entry)
        rate = mock_current_rate(bid=Decimal("1.0900"), ask=Decimal("1.0902"))

        with patch("tradingsystem.services.position_service.rateservice_client") as mock_rateservice:
            mock_rateservice.get_current_rate = AsyncMock(return_value=rate)

            pnl = await position_service.calculate_unrealized_pnl(position)

            # LONG: (current_bid - entry) * quantity = (1.0900 - 1.0850) * 1000 = 5.00
            assert pnl == Decimal("5.00")

    @pytest.mark.asyncio
    async def test_unrealized_pnl_short_profit(self, mock_current_rate, mock_position):
        """Calculate unrealized P&L for SHORT position in profit."""
        position = mock_position(
            side=PositionSide.SHORT,
            entry_price=Decimal("1.0900"),
            quantity=Decimal("1000"),
            status=PositionStatus.OPEN,
        )

        # Current ask is 1.0852 (lower than entry)
        rate = mock_current_rate(bid=Decimal("1.0850"), ask=Decimal("1.0852"))

        with patch("tradingsystem.services.position_service.rateservice_client") as mock_rateservice:
            mock_rateservice.get_current_rate = AsyncMock(return_value=rate)

            pnl = await position_service.calculate_unrealized_pnl(position)

            # SHORT: (entry - current_ask) * quantity = (1.0900 - 1.0852) * 1000 = 4.80
            assert pnl == Decimal("4.80")

    @pytest.mark.asyncio
    async def test_unrealized_pnl_closed_position(self, mock_position):
        """Closed positions should return realized P&L."""
        position = mock_position(
            status=PositionStatus.CLOSED,
            pnl=Decimal("10.00"),
        )

        pnl = await position_service.calculate_unrealized_pnl(position)

        # Closed positions return their realized P&L
        assert pnl == Decimal("10.00")

    @pytest.mark.asyncio
    async def test_unrealized_pnl_closed_position_no_pnl(self, mock_position):
        """Closed positions with no P&L should return 0."""
        position = mock_position(
            status=PositionStatus.CLOSED,
            pnl=None,
        )

        pnl = await position_service.calculate_unrealized_pnl(position)

        assert pnl == Decimal("0")
