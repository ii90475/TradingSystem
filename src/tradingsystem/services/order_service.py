"""Order service for managing trading orders."""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from tradingsystem.core.database import get_cursor
from tradingsystem.core.rateservice import rateservice_client
from tradingsystem.models.order import (
    Order,
    OrderCreate,
    OrderSide,
    OrderStatus,
    OrderType,
    TradingMode,
)

logger = logging.getLogger(__name__)


async def create_order(order: OrderCreate) -> Order:
    """
    Create a new order.

    For paper trading, market orders are filled immediately.
    For limit/stop orders, they remain pending until conditions are met.

    Args:
        order: Order creation request

    Returns:
        Created Order object
    """
    async with get_cursor() as cur:
        await cur.execute(
            """
            INSERT INTO orders (
                strategy_id, instrument, side, order_type, quantity, price, status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, external_id, strategy_id, instrument, side, order_type,
                      quantity, price, status, created_at, filled_at, filled_price, filled_quantity
            """,
            (
                order.strategy_id,
                order.instrument,
                order.side.value,
                order.order_type.value,
                order.quantity,
                order.price,
                OrderStatus.PENDING.value,
            ),
        )
        row = await cur.fetchone()
        await cur.connection.commit()

        created_order = _row_to_order(row)

        logger.info(
            "order_created",
            extra={
                "event": "order",
                "action": "create",
                "order_id": str(created_order.id),
                "instrument": order.instrument,
                "side": order.side.value,
                "type": order.order_type.value,
                "quantity": str(order.quantity),
            },
        )

        # For paper trading, fill market orders immediately
        if order.mode == TradingMode.PAPER and order.order_type == OrderType.MARKET:
            created_order = await fill_order_at_market(created_order.id)

        return created_order


async def fill_order_at_market(order_id: UUID) -> Order:
    """
    Fill an order at current market price.

    Fetches the current rate and fills the order with appropriate slippage.

    Args:
        order_id: Order UUID to fill

    Returns:
        Updated Order with fill details
    """
    order = await get_order(order_id)
    if not order:
        raise ValueError(f"Order not found: {order_id}")

    if order.status != OrderStatus.PENDING:
        raise ValueError(f"Order is not pending: {order.status}")

    # Get current market price
    rate = await rateservice_client.get_current_rate(order.instrument)

    # Use bid for sells, ask for buys (includes spread)
    if order.side == OrderSide.BUY:
        fill_price = rate.ask
    else:
        fill_price = rate.bid

    # Add small slippage for realism (0.05%)
    slippage = fill_price * Decimal("0.0005")
    if order.side == OrderSide.BUY:
        fill_price += slippage
    else:
        fill_price -= slippage

    return await fill_order(order_id, fill_price, order.quantity)


async def fill_order(
    order_id: UUID,
    fill_price: Decimal,
    fill_quantity: Decimal,
) -> Order:
    """
    Fill an order at specified price and quantity.

    Args:
        order_id: Order UUID
        fill_price: Price at which order was filled
        fill_quantity: Quantity filled

    Returns:
        Updated Order object
    """
    now = datetime.now(timezone.utc)

    async with get_cursor() as cur:
        await cur.execute(
            """
            UPDATE orders
            SET status = %s, filled_at = %s, filled_price = %s, filled_quantity = %s
            WHERE id = %s
            RETURNING id, external_id, strategy_id, instrument, side, order_type,
                      quantity, price, status, created_at, filled_at, filled_price, filled_quantity
            """,
            (OrderStatus.FILLED.value, now, fill_price, fill_quantity, order_id),
        )
        row = await cur.fetchone()
        await cur.connection.commit()

        if not row:
            raise ValueError(f"Order not found: {order_id}")

        order = _row_to_order(row)

        logger.info(
            "order_filled",
            extra={
                "event": "order",
                "action": "fill",
                "order_id": str(order_id),
                "fill_price": str(fill_price),
                "fill_quantity": str(fill_quantity),
            },
        )

        return order


async def cancel_order(order_id: UUID) -> Order:
    """
    Cancel a pending order.

    Args:
        order_id: Order UUID to cancel

    Returns:
        Updated Order object
    """
    async with get_cursor() as cur:
        await cur.execute(
            """
            UPDATE orders
            SET status = %s
            WHERE id = %s AND status = %s
            RETURNING id, external_id, strategy_id, instrument, side, order_type,
                      quantity, price, status, created_at, filled_at, filled_price, filled_quantity
            """,
            (OrderStatus.CANCELLED.value, order_id, OrderStatus.PENDING.value),
        )
        row = await cur.fetchone()
        await cur.connection.commit()

        if not row:
            raise ValueError(f"Order not found or not pending: {order_id}")

        order = _row_to_order(row)

        logger.info(
            "order_cancelled",
            extra={
                "event": "order",
                "action": "cancel",
                "order_id": str(order_id),
            },
        )

        return order


async def get_order(order_id: UUID) -> Order | None:
    """Get an order by ID."""
    async with get_cursor() as cur:
        await cur.execute(
            """
            SELECT id, external_id, strategy_id, instrument, side, order_type,
                   quantity, price, status, created_at, filled_at, filled_price, filled_quantity
            FROM orders
            WHERE id = %s
            """,
            (order_id,),
        )
        row = await cur.fetchone()
        return _row_to_order(row) if row else None


async def list_orders(
    status: OrderStatus | None = None,
    instrument: str | None = None,
    strategy_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Order]:
    """List orders with optional filtering."""
    conditions = []
    params: list[Any] = []

    if status:
        conditions.append("status = %s")
        params.append(status.value)

    if instrument:
        conditions.append("instrument = %s")
        params.append(instrument)

    if strategy_id:
        conditions.append("strategy_id = %s")
        params.append(strategy_id)

    where_clause = " AND ".join(conditions) if conditions else "1=1"
    params.extend([limit, offset])

    async with get_cursor() as cur:
        await cur.execute(
            f"""
            SELECT id, external_id, strategy_id, instrument, side, order_type,
                   quantity, price, status, created_at, filled_at, filled_price, filled_quantity
            FROM orders
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            params,
        )
        rows = await cur.fetchall()
        return [_row_to_order(row) for row in rows]


async def get_pending_orders(instrument: str | None = None) -> list[Order]:
    """Get all pending orders, optionally filtered by instrument."""
    return await list_orders(status=OrderStatus.PENDING, instrument=instrument)


async def count_orders(status: OrderStatus | None = None) -> int:
    """Count orders with optional status filter."""
    async with get_cursor() as cur:
        if status:
            await cur.execute(
                "SELECT COUNT(*) as count FROM orders WHERE status = %s",
                (status.value,),
            )
        else:
            await cur.execute("SELECT COUNT(*) as count FROM orders")
        row = await cur.fetchone()
        return row["count"]


def _row_to_order(row: dict) -> Order:
    """Convert database row to Order object."""
    return Order(
        id=row["id"],
        external_id=row["external_id"],
        strategy_id=row["strategy_id"],
        instrument=row["instrument"],
        side=OrderSide(row["side"]),
        order_type=OrderType(row["order_type"]),
        quantity=row["quantity"],
        price=row["price"],
        status=OrderStatus(row["status"]),
        created_at=row["created_at"],
        filled_at=row["filled_at"],
        filled_price=row["filled_price"],
        filled_quantity=row["filled_quantity"],
    )
