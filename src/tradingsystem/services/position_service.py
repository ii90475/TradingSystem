"""Position service for managing trading positions."""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from tradingsystem.core.database import get_cursor
from tradingsystem.core.rateservice import rateservice_client
from tradingsystem.models.position import (
    Position,
    PositionCreate,
    PositionSide,
    PositionStatus,
    PositionSummary,
)

logger = logging.getLogger(__name__)


async def open_position(position: PositionCreate) -> Position:
    """
    Open a new position.

    Args:
        position: Position creation request

    Returns:
        Created Position object
    """
    now = datetime.now(timezone.utc)

    async with get_cursor() as cur:
        await cur.execute(
            """
            INSERT INTO positions (
                instrument, side, quantity, entry_price, entry_time, status, strategy_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, instrument, side, quantity, entry_price, entry_time,
                      exit_price, exit_time, status, strategy_id, pnl, pnl_percent
            """,
            (
                position.instrument,
                position.side.value,
                position.quantity,
                position.entry_price,
                now,
                PositionStatus.OPEN.value,
                position.strategy_id,
            ),
        )
        row = await cur.fetchone()
        await cur.connection.commit()

        created_position = _row_to_position(row)

        logger.info(
            "position_opened",
            extra={
                "event": "position",
                "action": "open",
                "position_id": str(created_position.id),
                "instrument": position.instrument,
                "side": position.side.value,
                "quantity": str(position.quantity),
                "entry_price": str(position.entry_price),
            },
        )

        return created_position


async def close_position(position_id: UUID, exit_price: Decimal) -> Position:
    """
    Close an open position.

    Args:
        position_id: Position UUID to close
        exit_price: Price at which to close

    Returns:
        Updated Position with P&L
    """
    position = await get_position(position_id)
    if not position:
        raise ValueError(f"Position not found: {position_id}")

    if position.status != PositionStatus.OPEN:
        raise ValueError(f"Position is not open: {position.status}")

    # Calculate P&L
    if position.side == PositionSide.LONG:
        pnl = (exit_price - position.entry_price) * position.quantity
    else:
        pnl = (position.entry_price - exit_price) * position.quantity

    pnl_percent = (pnl / (position.entry_price * position.quantity)) * 100

    now = datetime.now(timezone.utc)

    async with get_cursor() as cur:
        await cur.execute(
            """
            UPDATE positions
            SET exit_price = %s, exit_time = %s, status = %s, pnl = %s, pnl_percent = %s
            WHERE id = %s
            RETURNING id, instrument, side, quantity, entry_price, entry_time,
                      exit_price, exit_time, status, strategy_id, pnl, pnl_percent
            """,
            (
                exit_price,
                now,
                PositionStatus.CLOSED.value,
                pnl,
                pnl_percent,
                position_id,
            ),
        )
        row = await cur.fetchone()
        await cur.connection.commit()

        closed_position = _row_to_position(row)

        logger.info(
            "position_closed",
            extra={
                "event": "position",
                "action": "close",
                "position_id": str(position_id),
                "exit_price": str(exit_price),
                "pnl": str(pnl),
                "pnl_percent": str(pnl_percent),
            },
        )

        return closed_position


async def close_position_at_market(position_id: UUID) -> Position:
    """
    Close a position at current market price.

    Args:
        position_id: Position UUID to close

    Returns:
        Updated Position with P&L
    """
    position = await get_position(position_id)
    if not position:
        raise ValueError(f"Position not found: {position_id}")

    # Get current market price
    rate = await rateservice_client.get_current_rate(position.instrument)

    # Use bid for longs (selling), ask for shorts (buying to cover)
    if position.side == PositionSide.LONG:
        exit_price = rate.bid
    else:
        exit_price = rate.ask

    # Add small slippage
    slippage = exit_price * Decimal("0.0005")
    if position.side == PositionSide.LONG:
        exit_price -= slippage
    else:
        exit_price += slippage

    return await close_position(position_id, exit_price)


async def get_position(position_id: UUID) -> Position | None:
    """Get a position by ID."""
    async with get_cursor() as cur:
        await cur.execute(
            """
            SELECT id, instrument, side, quantity, entry_price, entry_time,
                   exit_price, exit_time, status, strategy_id, pnl, pnl_percent
            FROM positions
            WHERE id = %s
            """,
            (position_id,),
        )
        row = await cur.fetchone()
        return _row_to_position(row) if row else None


async def list_positions(
    status: PositionStatus | None = None,
    instrument: str | None = None,
    strategy_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Position]:
    """List positions with optional filtering."""
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
            SELECT id, instrument, side, quantity, entry_price, entry_time,
                   exit_price, exit_time, status, strategy_id, pnl, pnl_percent
            FROM positions
            WHERE {where_clause}
            ORDER BY entry_time DESC
            LIMIT %s OFFSET %s
            """,
            params,
        )
        rows = await cur.fetchall()
        return [_row_to_position(row) for row in rows]


async def get_open_positions(instrument: str | None = None) -> list[Position]:
    """Get all open positions."""
    return await list_positions(status=PositionStatus.OPEN, instrument=instrument)


async def get_position_summary() -> PositionSummary:
    """Get portfolio position summary with P&L calculations."""
    async with get_cursor() as cur:
        # Get counts and realized P&L
        await cur.execute(
            """
            SELECT
                COUNT(*) as total_positions,
                COUNT(*) FILTER (WHERE status = 'OPEN') as open_positions,
                COUNT(*) FILTER (WHERE status = 'CLOSED') as closed_positions,
                COALESCE(SUM(pnl) FILTER (WHERE status = 'CLOSED'), 0) as realized_pnl
            FROM positions
            """
        )
        row = await cur.fetchone()

        total_positions = row["total_positions"]
        open_positions = row["open_positions"]
        closed_positions = row["closed_positions"]
        realized_pnl = Decimal(str(row["realized_pnl"]))

        # Calculate unrealized P&L for open positions
        unrealized_pnl = Decimal("0")
        if open_positions > 0:
            open_pos_list = await get_open_positions()
            for pos in open_pos_list:
                try:
                    rate = await rateservice_client.get_current_rate(pos.instrument)
                    current_price = rate.bid if pos.side == PositionSide.LONG else rate.ask

                    if pos.side == PositionSide.LONG:
                        pnl = (current_price - pos.entry_price) * pos.quantity
                    else:
                        pnl = (pos.entry_price - current_price) * pos.quantity

                    unrealized_pnl += pnl
                except Exception as e:
                    logger.warning(f"Failed to get rate for {pos.instrument}: {e}")

        total_pnl = realized_pnl + unrealized_pnl

        return PositionSummary(
            total_positions=total_positions,
            open_positions=open_positions,
            closed_positions=closed_positions,
            total_pnl=total_pnl,
            unrealized_pnl=unrealized_pnl,
            realized_pnl=realized_pnl,
        )


async def calculate_unrealized_pnl(position: Position) -> Decimal:
    """Calculate unrealized P&L for an open position."""
    if position.status != PositionStatus.OPEN:
        return position.pnl or Decimal("0")

    rate = await rateservice_client.get_current_rate(position.instrument)
    current_price = rate.bid if position.side == PositionSide.LONG else rate.ask

    if position.side == PositionSide.LONG:
        return (current_price - position.entry_price) * position.quantity
    else:
        return (position.entry_price - current_price) * position.quantity


def _row_to_position(row: dict) -> Position:
    """Convert database row to Position object."""
    return Position(
        id=row["id"],
        instrument=row["instrument"],
        side=PositionSide(row["side"]),
        quantity=row["quantity"],
        entry_price=row["entry_price"],
        entry_time=row["entry_time"],
        exit_price=row["exit_price"],
        exit_time=row["exit_time"],
        status=PositionStatus(row["status"]),
        strategy_id=row["strategy_id"],
        pnl=row["pnl"],
        pnl_percent=row["pnl_percent"],
    )
