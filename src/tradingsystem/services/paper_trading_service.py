"""Paper trading service for simulated trading execution."""

import logging
from decimal import Decimal
from uuid import UUID

from tradingsystem.core.rateservice import rateservice_client
from tradingsystem.models.order import Order, OrderCreate, OrderSide, OrderStatus, OrderType, TradingMode
from tradingsystem.models.position import Position, PositionCreate, PositionSide, PositionStatus
from tradingsystem.services import order_service, position_service

logger = logging.getLogger(__name__)


async def execute_trade(
    instrument: str,
    side: OrderSide,
    quantity: Decimal,
    strategy_id: str | None = None,
) -> tuple[Order, Position]:
    """
    Execute a paper trade (create order and open position).

    This is the primary entry point for paper trading. It:
    1. Creates a market order
    2. Fills it at current market price
    3. Opens a corresponding position

    Args:
        instrument: Currency pair (e.g., "EUR_USD")
        side: BUY or SELL
        quantity: Position size
        strategy_id: Optional strategy identifier

    Returns:
        Tuple of (Order, Position)
    """
    # Create and fill market order
    order = await order_service.create_order(
        OrderCreate(
            instrument=instrument,
            side=side,
            order_type=OrderType.MARKET,
            quantity=quantity,
            strategy_id=strategy_id,
            mode=TradingMode.PAPER,
        )
    )

    if order.status != OrderStatus.FILLED:
        raise RuntimeError(f"Market order was not filled: {order.status}")

    # Determine position side
    position_side = PositionSide.LONG if side == OrderSide.BUY else PositionSide.SHORT

    # Open position at fill price
    position = await position_service.open_position(
        PositionCreate(
            instrument=instrument,
            side=position_side,
            quantity=order.filled_quantity or quantity,
            entry_price=order.filled_price or Decimal("0"),
            strategy_id=strategy_id,
        )
    )

    logger.info(
        "paper_trade_executed",
        extra={
            "event": "paper_trade",
            "action": "execute",
            "order_id": str(order.id),
            "position_id": str(position.id),
            "instrument": instrument,
            "side": side.value,
            "quantity": str(quantity),
            "fill_price": str(order.filled_price),
        },
    )

    return order, position


async def close_trade(position_id: UUID) -> tuple[Order, Position]:
    """
    Close an existing paper trade.

    Creates a closing order and closes the position.

    Args:
        position_id: Position UUID to close

    Returns:
        Tuple of (Order, Position)
    """
    position = await position_service.get_position(position_id)
    if not position:
        raise ValueError(f"Position not found: {position_id}")

    if position.status != PositionStatus.OPEN:
        raise ValueError(f"Position is not open: {position.status}")

    # Create closing order (opposite side)
    close_side = OrderSide.SELL if position.side == PositionSide.LONG else OrderSide.BUY

    order = await order_service.create_order(
        OrderCreate(
            instrument=position.instrument,
            side=close_side,
            order_type=OrderType.MARKET,
            quantity=position.quantity,
            strategy_id=position.strategy_id,
            mode=TradingMode.PAPER,
        )
    )

    if order.status != OrderStatus.FILLED:
        raise RuntimeError(f"Closing order was not filled: {order.status}")

    # Close position at fill price
    closed_position = await position_service.close_position(
        position_id,
        order.filled_price or Decimal("0"),
    )

    logger.info(
        "paper_trade_closed",
        extra={
            "event": "paper_trade",
            "action": "close",
            "order_id": str(order.id),
            "position_id": str(position_id),
            "exit_price": str(order.filled_price),
            "pnl": str(closed_position.pnl),
        },
    )

    return order, closed_position


async def get_account_summary() -> dict:
    """
    Get paper trading account summary.

    Returns:
        Dict with account information
    """
    position_summary = await position_service.get_position_summary()
    pending_orders = await order_service.count_orders(OrderStatus.PENDING)

    return {
        "mode": "PAPER",
        "positions": {
            "total": position_summary.total_positions,
            "open": position_summary.open_positions,
            "closed": position_summary.closed_positions,
        },
        "pending_orders": pending_orders,
        "pnl": {
            "total": str(position_summary.total_pnl),
            "realized": str(position_summary.realized_pnl),
            "unrealized": str(position_summary.unrealized_pnl),
        },
    }


async def get_current_price(instrument: str) -> dict:
    """
    Get current bid/ask for an instrument.

    Args:
        instrument: Currency pair

    Returns:
        Dict with bid, ask, spread
    """
    rate = await rateservice_client.get_current_rate(instrument)
    spread = rate.ask - rate.bid

    return {
        "instrument": instrument,
        "bid": str(rate.bid),
        "ask": str(rate.ask),
        "spread": str(spread),
        "time": rate.time.isoformat(),
        "tradeable": rate.tradeable,
    }
