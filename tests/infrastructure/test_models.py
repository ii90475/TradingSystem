"""Tests for data models."""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from tradingsystem.models.order import (
    Order,
    OrderCreate,
    OrderSide,
    OrderStatus,
    OrderType,
    TradingMode,
)
from tradingsystem.models.position import (
    Position,
    PositionClose,
    PositionCreate,
    PositionSide,
    PositionStatus,
    PositionSummary,
)
from tradingsystem.models.signal import Signal, SignalCreate, SignalType


class TestOrderModel:
    """Tests for Order model."""

    def test_order_creation(self):
        """Should create order with all fields."""
        order = Order(
            id=uuid4(),
            external_id="oanda-123",
            strategy_id="ma_crossover",
            instrument="EUR_USD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("1000"),
            status=OrderStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )

        assert order.side == OrderSide.BUY
        assert order.order_type == OrderType.MARKET
        assert order.status == OrderStatus.PENDING

    def test_order_side_enum(self):
        """Should enforce OrderSide enum values."""
        assert OrderSide.BUY.value == "BUY"
        assert OrderSide.SELL.value == "SELL"

    def test_order_type_enum(self):
        """Should enforce OrderType enum values."""
        assert OrderType.MARKET.value == "MARKET"
        assert OrderType.LIMIT.value == "LIMIT"
        assert OrderType.STOP.value == "STOP"

    def test_order_status_enum(self):
        """Should enforce OrderStatus enum values."""
        assert OrderStatus.PENDING.value == "PENDING"
        assert OrderStatus.FILLED.value == "FILLED"
        assert OrderStatus.CANCELLED.value == "CANCELLED"
        assert OrderStatus.REJECTED.value == "REJECTED"

    def test_order_optional_fields(self):
        """Should allow optional fields to be None."""
        order = Order(
            id=uuid4(),
            instrument="EUR_USD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("1000"),
            status=OrderStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )

        assert order.external_id is None
        assert order.strategy_id is None
        assert order.price is None
        assert order.filled_at is None
        assert order.filled_price is None


class TestOrderCreateModel:
    """Tests for OrderCreate model."""

    def test_order_create_minimal(self):
        """Should create with required fields only."""
        order_create = OrderCreate(
            instrument="EUR_USD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("1000"),
        )

        assert order_create.mode == TradingMode.PAPER
        assert order_create.price is None

    def test_order_create_limit_with_price(self):
        """Should accept price for limit orders."""
        order_create = OrderCreate(
            instrument="EUR_USD",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("1000"),
            price=Decimal("1.0850"),
        )

        assert order_create.price == Decimal("1.0850")


class TestPositionModel:
    """Tests for Position model."""

    def test_position_creation(self):
        """Should create position with all fields."""
        position = Position(
            id=uuid4(),
            instrument="EUR_USD",
            side=PositionSide.LONG,
            quantity=Decimal("1000"),
            entry_price=Decimal("1.0850"),
            entry_time=datetime.now(timezone.utc),
            status=PositionStatus.OPEN,
        )

        assert position.side == PositionSide.LONG
        assert position.status == PositionStatus.OPEN

    def test_position_side_enum(self):
        """Should enforce PositionSide enum values."""
        assert PositionSide.LONG.value == "LONG"
        assert PositionSide.SHORT.value == "SHORT"

    def test_position_status_enum(self):
        """Should enforce PositionStatus enum values."""
        assert PositionStatus.OPEN.value == "OPEN"
        assert PositionStatus.CLOSED.value == "CLOSED"

    def test_position_closed_with_pnl(self):
        """Should include P&L when closed."""
        position = Position(
            id=uuid4(),
            instrument="EUR_USD",
            side=PositionSide.LONG,
            quantity=Decimal("1000"),
            entry_price=Decimal("1.0850"),
            entry_time=datetime.now(timezone.utc),
            exit_price=Decimal("1.0900"),
            exit_time=datetime.now(timezone.utc),
            status=PositionStatus.CLOSED,
            pnl=Decimal("50.00"),
            pnl_percent=Decimal("0.46"),
        )

        assert position.exit_price == Decimal("1.0900")
        assert position.pnl == Decimal("50.00")


class TestPositionSummaryModel:
    """Tests for PositionSummary model."""

    def test_position_summary(self):
        """Should aggregate position statistics."""
        summary = PositionSummary(
            total_positions=10,
            open_positions=3,
            closed_positions=7,
            total_pnl=Decimal("500.00"),
            unrealized_pnl=Decimal("50.00"),
            realized_pnl=Decimal("450.00"),
        )

        assert summary.total_positions == 10
        assert summary.open_positions == 3
        assert summary.total_pnl == Decimal("500.00")


class TestSignalModel:
    """Tests for Signal model."""

    def test_signal_creation(self):
        """Should create signal with all fields."""
        signal = Signal(
            id=uuid4(),
            time=datetime.now(timezone.utc),
            strategy_id="ma_crossover",
            instrument="EUR_USD",
            signal_type=SignalType.BUY,
            strength=Decimal("0.85"),
            reason="MA crossover detected",
        )

        assert signal.signal_type == SignalType.BUY
        assert signal.strength == Decimal("0.85")

    def test_signal_type_enum(self):
        """Should enforce SignalType enum values."""
        assert SignalType.BUY.value == "BUY"
        assert SignalType.SELL.value == "SELL"
        assert SignalType.HOLD.value == "HOLD"

    def test_signal_strength_bounds(self):
        """Should enforce strength between 0 and 1."""
        # Valid strength
        signal = Signal(
            time=datetime.now(timezone.utc),
            strategy_id="test",
            instrument="EUR_USD",
            signal_type=SignalType.BUY,
            strength=Decimal("0.5"),
        )
        assert signal.strength == Decimal("0.5")

    def test_signal_strength_invalid_high(self):
        """Should reject strength > 1."""
        with pytest.raises(ValidationError):
            Signal(
                time=datetime.now(timezone.utc),
                strategy_id="test",
                instrument="EUR_USD",
                signal_type=SignalType.BUY,
                strength=Decimal("1.5"),
            )

    def test_signal_strength_invalid_negative(self):
        """Should reject negative strength."""
        with pytest.raises(ValidationError):
            Signal(
                time=datetime.now(timezone.utc),
                strategy_id="test",
                instrument="EUR_USD",
                signal_type=SignalType.BUY,
                strength=Decimal("-0.5"),
            )

    def test_signal_default_strength(self):
        """Should default strength to 0.5."""
        signal = Signal(
            time=datetime.now(timezone.utc),
            strategy_id="test",
            instrument="EUR_USD",
            signal_type=SignalType.BUY,
        )
        assert signal.strength == Decimal("0.5")

    def test_signal_with_metadata(self):
        """Should accept metadata dict."""
        signal = Signal(
            time=datetime.now(timezone.utc),
            strategy_id="test",
            instrument="EUR_USD",
            signal_type=SignalType.BUY,
            metadata={"sma_20": 1.0860, "sma_50": 1.0840},
        )

        assert signal.metadata["sma_20"] == 1.0860
