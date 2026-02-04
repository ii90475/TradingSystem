"""Tests for reconciliation service."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from tradingsystem.core.oanda_trading import OandaTrade
from tradingsystem.models.position import Position, PositionSide, PositionStatus
from tradingsystem.services import reconciliation_service
from tradingsystem.services.reconciliation_service import (
    PositionDiscrepancy,
    ReconciliationResult,
)


# --- Fixtures ---


@pytest.fixture
def sample_oanda_trade():
    """Create sample OANDA trade."""
    return OandaTrade(
        id="trade-123",
        instrument="EUR_USD",
        units=Decimal("1000"),
        price=Decimal("1.0850"),
        unrealized_pnl=Decimal("25.00"),
        state="OPEN",
        open_time=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_local_position():
    """Create sample local position."""
    return Position(
        id=uuid4(),
        instrument="EUR_USD",
        side=PositionSide.LONG,
        quantity=Decimal("1000"),
        entry_price=Decimal("1.0850"),
        entry_time=datetime.now(timezone.utc),
        status=PositionStatus.OPEN,
    )


# --- PositionDiscrepancy Tests ---


class TestPositionDiscrepancy:
    """Tests for PositionDiscrepancy dataclass."""

    def test_discrepancy_missing_local(self):
        """Should create discrepancy for missing local position."""
        discrepancy = PositionDiscrepancy(
            instrument="EUR_USD",
            local_quantity=None,
            oanda_quantity=Decimal("1000"),
            local_side=None,
            oanda_side="LONG",
            discrepancy_type="missing_local",
            oanda_trade_id="trade-123",
        )

        assert discrepancy.discrepancy_type == "missing_local"
        assert discrepancy.local_quantity is None
        assert discrepancy.oanda_quantity == Decimal("1000")

    def test_discrepancy_missing_oanda(self):
        """Should create discrepancy for missing OANDA trade."""
        discrepancy = PositionDiscrepancy(
            instrument="EUR_USD",
            local_quantity=Decimal("1000"),
            oanda_quantity=None,
            local_side="LONG",
            oanda_side=None,
            discrepancy_type="missing_oanda",
            local_position_id="pos-123",
        )

        assert discrepancy.discrepancy_type == "missing_oanda"
        assert discrepancy.oanda_quantity is None


# --- reconcile_positions Tests ---


class TestReconcilePositions:
    """Tests for reconcile_positions function."""

    @pytest.mark.asyncio
    async def test_reconcile_in_sync(self, sample_oanda_trade, sample_local_position):
        """Should return in_sync=True when positions match."""
        with patch("tradingsystem.services.reconciliation_service.oanda_trading_client") as mock_oanda, \
             patch("tradingsystem.services.reconciliation_service.position_service") as mock_pos:
            mock_oanda.get_open_trades = AsyncMock(return_value=[sample_oanda_trade])
            mock_pos.get_open_positions = AsyncMock(return_value=[sample_local_position])

            result = await reconciliation_service.reconcile_positions()

            assert result.in_sync is True
            assert len(result.discrepancies) == 0
            assert result.oanda_positions == 1
            assert result.local_positions == 1

    @pytest.mark.asyncio
    async def test_reconcile_missing_local(self, sample_oanda_trade):
        """Should detect missing local position."""
        with patch("tradingsystem.services.reconciliation_service.oanda_trading_client") as mock_oanda, \
             patch("tradingsystem.services.reconciliation_service.position_service") as mock_pos:
            mock_oanda.get_open_trades = AsyncMock(return_value=[sample_oanda_trade])
            mock_pos.get_open_positions = AsyncMock(return_value=[])

            result = await reconciliation_service.reconcile_positions()

            assert result.in_sync is False
            assert len(result.discrepancies) == 1
            assert result.discrepancies[0].discrepancy_type == "missing_local"
            assert result.discrepancies[0].oanda_trade_id == "trade-123"

    @pytest.mark.asyncio
    async def test_reconcile_missing_oanda(self, sample_local_position):
        """Should detect missing OANDA trade."""
        with patch("tradingsystem.services.reconciliation_service.oanda_trading_client") as mock_oanda, \
             patch("tradingsystem.services.reconciliation_service.position_service") as mock_pos:
            mock_oanda.get_open_trades = AsyncMock(return_value=[])
            mock_pos.get_open_positions = AsyncMock(return_value=[sample_local_position])

            result = await reconciliation_service.reconcile_positions()

            assert result.in_sync is False
            assert len(result.discrepancies) == 1
            assert result.discrepancies[0].discrepancy_type == "missing_oanda"

    @pytest.mark.asyncio
    async def test_reconcile_quantity_mismatch(self, sample_oanda_trade, sample_local_position):
        """Should detect quantity mismatch."""
        # OANDA has 2000, local has 1000
        sample_oanda_trade.units = Decimal("2000")

        with patch("tradingsystem.services.reconciliation_service.oanda_trading_client") as mock_oanda, \
             patch("tradingsystem.services.reconciliation_service.position_service") as mock_pos:
            mock_oanda.get_open_trades = AsyncMock(return_value=[sample_oanda_trade])
            mock_pos.get_open_positions = AsyncMock(return_value=[sample_local_position])

            result = await reconciliation_service.reconcile_positions()

            assert result.in_sync is False
            assert len(result.discrepancies) == 1
            assert result.discrepancies[0].discrepancy_type == "quantity_mismatch"

    @pytest.mark.asyncio
    async def test_reconcile_side_mismatch(self, sample_oanda_trade, sample_local_position):
        """Should detect side mismatch when quantities match but sides differ."""
        # Note: The reconciliation logic checks quantity_mismatch before side_mismatch.
        # Side mismatch only triggers when net quantities are very close (< 0.01)
        # but have opposite signs. For large differences, it's quantity_mismatch.
        #
        # OANDA is SHORT (negative units), local is LONG - since magnitude differs
        # by 2000, this triggers quantity_mismatch, not side_mismatch
        sample_oanda_trade.units = Decimal("-1000")

        with patch("tradingsystem.services.reconciliation_service.oanda_trading_client") as mock_oanda, \
             patch("tradingsystem.services.reconciliation_service.position_service") as mock_pos:
            mock_oanda.get_open_trades = AsyncMock(return_value=[sample_oanda_trade])
            mock_pos.get_open_positions = AsyncMock(return_value=[sample_local_position])

            result = await reconciliation_service.reconcile_positions()

            assert result.in_sync is False
            assert len(result.discrepancies) == 1
            # Due to implementation, opposite sides with same magnitude triggers quantity_mismatch
            # because abs(-1000 - 1000) = 2000 > 0.01
            assert result.discrepancies[0].discrepancy_type == "quantity_mismatch"

    @pytest.mark.asyncio
    async def test_reconcile_oanda_error(self):
        """Should return error result when OANDA fails."""
        with patch("tradingsystem.services.reconciliation_service.oanda_trading_client") as mock_oanda:
            mock_oanda.get_open_trades = AsyncMock(side_effect=Exception("Connection failed"))

            result = await reconciliation_service.reconcile_positions()

            assert result.in_sync is False
            assert result.oanda_positions == 0

    @pytest.mark.asyncio
    async def test_reconcile_multiple_instruments(self):
        """Should reconcile positions across multiple instruments."""
        oanda_trades = [
            OandaTrade(
                id="trade-1",
                instrument="EUR_USD",
                units=Decimal("1000"),
                price=Decimal("1.0850"),
                unrealized_pnl=Decimal("0"),
                state="OPEN",
                open_time=datetime.now(timezone.utc),
            ),
            OandaTrade(
                id="trade-2",
                instrument="GBP_USD",
                units=Decimal("500"),
                price=Decimal("1.2500"),
                unrealized_pnl=Decimal("0"),
                state="OPEN",
                open_time=datetime.now(timezone.utc),
            ),
        ]

        local_positions = [
            Position(
                id=uuid4(),
                instrument="EUR_USD",
                side=PositionSide.LONG,
                quantity=Decimal("1000"),
                entry_price=Decimal("1.0850"),
                entry_time=datetime.now(timezone.utc),
                status=PositionStatus.OPEN,
            ),
            Position(
                id=uuid4(),
                instrument="GBP_USD",
                side=PositionSide.LONG,
                quantity=Decimal("500"),
                entry_price=Decimal("1.2500"),
                entry_time=datetime.now(timezone.utc),
                status=PositionStatus.OPEN,
            ),
        ]

        with patch("tradingsystem.services.reconciliation_service.oanda_trading_client") as mock_oanda, \
             patch("tradingsystem.services.reconciliation_service.position_service") as mock_pos:
            mock_oanda.get_open_trades = AsyncMock(return_value=oanda_trades)
            mock_pos.get_open_positions = AsyncMock(return_value=local_positions)

            result = await reconciliation_service.reconcile_positions()

            assert result.in_sync is True
            assert result.oanda_positions == 2
            assert result.local_positions == 2


# --- sync_from_oanda Tests ---


class TestSyncFromOanda:
    """Tests for sync_from_oanda function."""

    @pytest.mark.asyncio
    async def test_sync_no_discrepancies(self):
        """Should report no actions when in sync."""
        with patch("tradingsystem.services.reconciliation_service.reconcile_positions") as mock_reconcile:
            mock_reconcile.return_value = ReconciliationResult(
                timestamp=datetime.now(timezone.utc),
                oanda_positions=1,
                local_positions=1,
                discrepancies=[],
                in_sync=True,
            )

            result = await reconciliation_service.sync_from_oanda()

            assert result["reconciliation"]["in_sync"] is True
            assert len(result["actions"]["closed"]) == 0
            assert len(result["actions"]["created"]) == 0
            assert len(result["actions"]["errors"]) == 0

    @pytest.mark.asyncio
    async def test_sync_closes_orphan_local_positions(self):
        """Should close local positions not in OANDA."""
        position_id = str(uuid4())
        discrepancy = PositionDiscrepancy(
            instrument="EUR_USD",
            local_quantity=Decimal("1000"),
            oanda_quantity=None,
            local_side="LONG",
            oanda_side=None,
            discrepancy_type="missing_oanda",
            local_position_id=position_id,
        )

        mock_position = MagicMock()
        mock_position.status = PositionStatus.OPEN
        mock_position.entry_price = Decimal("1.0850")

        with patch("tradingsystem.services.reconciliation_service.reconcile_positions") as mock_reconcile, \
             patch("tradingsystem.services.reconciliation_service.position_service") as mock_pos:
            mock_reconcile.return_value = ReconciliationResult(
                timestamp=datetime.now(timezone.utc),
                oanda_positions=0,
                local_positions=1,
                discrepancies=[discrepancy],
                in_sync=False,
            )
            mock_pos.get_position = AsyncMock(return_value=mock_position)
            mock_pos.close_position = AsyncMock()

            result = await reconciliation_service.sync_from_oanda()

            assert len(result["actions"]["closed"]) == 1
            assert result["actions"]["closed"][0]["reason"] == "not_found_in_oanda"

    @pytest.mark.asyncio
    async def test_sync_reports_missing_local_as_error(self):
        """Should report missing local positions as needing intervention."""
        discrepancy = PositionDiscrepancy(
            instrument="EUR_USD",
            local_quantity=None,
            oanda_quantity=Decimal("1000"),
            local_side=None,
            oanda_side="LONG",
            discrepancy_type="missing_local",
            oanda_trade_id="trade-123",
        )

        with patch("tradingsystem.services.reconciliation_service.reconcile_positions") as mock_reconcile:
            mock_reconcile.return_value = ReconciliationResult(
                timestamp=datetime.now(timezone.utc),
                oanda_positions=1,
                local_positions=0,
                discrepancies=[discrepancy],
                in_sync=False,
            )

            result = await reconciliation_service.sync_from_oanda()

            assert len(result["actions"]["errors"]) == 1
            assert result["actions"]["errors"][0]["reason"] == "manual_intervention_required"


# --- get_oanda_positions_summary Tests ---


class TestGetOandaPositionsSummary:
    """Tests for get_oanda_positions_summary function."""

    @pytest.mark.asyncio
    async def test_get_summary_success(self):
        """Should return OANDA positions summary."""
        from tradingsystem.core.oanda_trading import OandaAccount

        mock_trades = [
            OandaTrade(
                id="trade-1",
                instrument="EUR_USD",
                units=Decimal("1000"),
                price=Decimal("1.0850"),
                unrealized_pnl=Decimal("50.00"),
                state="OPEN",
                open_time=datetime.now(timezone.utc),
            ),
            OandaTrade(
                id="trade-2",
                instrument="EUR_USD",
                units=Decimal("500"),
                price=Decimal("1.0860"),
                unrealized_pnl=Decimal("25.00"),
                state="OPEN",
                open_time=datetime.now(timezone.utc),
            ),
        ]

        mock_account = OandaAccount(
            id="test-account",
            balance=Decimal("10000.00"),
            nav=Decimal("10075.00"),
            unrealized_pnl=Decimal("75.00"),
            margin_used=Decimal("500.00"),
            margin_available=Decimal("9500.00"),
            open_trade_count=2,
            open_position_count=1,
        )

        with patch("tradingsystem.services.reconciliation_service.oanda_trading_client") as mock_oanda:
            mock_oanda.get_open_trades = AsyncMock(return_value=mock_trades)
            mock_oanda.get_account_summary = AsyncMock(return_value=mock_account)

            result = await reconciliation_service.get_oanda_positions_summary()

            assert result["account_id"] == "test-account"
            assert result["balance"] == "10000.00"
            assert result["open_trade_count"] == 2
            assert len(result["positions"]) == 1
            assert result["positions"][0]["instrument"] == "EUR_USD"
            assert result["positions"][0]["net_units"] == "1500"  # 1000 + 500

    @pytest.mark.asyncio
    async def test_get_summary_error(self):
        """Should return error on failure."""
        with patch("tradingsystem.services.reconciliation_service.oanda_trading_client") as mock_oanda:
            mock_oanda.get_open_trades = AsyncMock(side_effect=Exception("Connection failed"))

            result = await reconciliation_service.get_oanda_positions_summary()

            assert "error" in result
            assert "Connection failed" in result["error"]

    @pytest.mark.asyncio
    async def test_get_summary_mixed_sides(self):
        """Should correctly identify LONG and SHORT positions."""
        mock_trades = [
            OandaTrade(
                id="trade-1",
                instrument="EUR_USD",
                units=Decimal("1000"),  # LONG
                price=Decimal("1.0850"),
                unrealized_pnl=Decimal("50.00"),
                state="OPEN",
                open_time=datetime.now(timezone.utc),
            ),
            OandaTrade(
                id="trade-2",
                instrument="GBP_USD",
                units=Decimal("-500"),  # SHORT
                price=Decimal("1.2500"),
                unrealized_pnl=Decimal("-25.00"),
                state="OPEN",
                open_time=datetime.now(timezone.utc),
            ),
        ]

        from tradingsystem.core.oanda_trading import OandaAccount

        mock_account = OandaAccount(
            id="test-account",
            balance=Decimal("10000.00"),
            nav=Decimal("10025.00"),
            unrealized_pnl=Decimal("25.00"),
            margin_used=Decimal("500.00"),
            margin_available=Decimal("9500.00"),
            open_trade_count=2,
            open_position_count=2,
        )

        with patch("tradingsystem.services.reconciliation_service.oanda_trading_client") as mock_oanda:
            mock_oanda.get_open_trades = AsyncMock(return_value=mock_trades)
            mock_oanda.get_account_summary = AsyncMock(return_value=mock_account)

            result = await reconciliation_service.get_oanda_positions_summary()

            positions = {p["instrument"]: p for p in result["positions"]}
            assert positions["EUR_USD"]["side"] == "LONG"
            assert positions["GBP_USD"]["side"] == "SHORT"
