"""Signal service for storing and retrieving trading signals."""

import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from tradingsystem.core.database import get_cursor
from tradingsystem.models.signal import Signal, SignalCreate, SignalType

logger = logging.getLogger(__name__)


async def save_signal(signal: Signal) -> Signal:
    """
    Save a signal to the database.

    Args:
        signal: Signal object to save

    Returns:
        Signal with generated ID
    """
    async with get_cursor() as cur:
        await cur.execute(
            """
            INSERT INTO signals (time, strategy_id, instrument, signal_type, strength, reason, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, time, strategy_id, instrument, signal_type, strength, reason, metadata
            """,
            (
                signal.time,
                signal.strategy_id,
                signal.instrument,
                signal.signal_type.value,
                signal.strength,
                signal.reason,
                json.dumps(signal.metadata) if signal.metadata else None,
            ),
        )
        row = await cur.fetchone()
        await cur.connection.commit()

        logger.info(
            "signal_saved",
            extra={
                "event": "signal",
                "action": "save",
                "strategy_id": signal.strategy_id,
                "instrument": signal.instrument,
                "signal_type": signal.signal_type.value,
                "id": str(row["id"]),
            },
        )

        return Signal(
            id=row["id"],
            time=row["time"],
            strategy_id=row["strategy_id"],
            instrument=row["instrument"],
            signal_type=SignalType(row["signal_type"]),
            strength=float(row["strength"]) if row["strength"] else None,
            reason=row["reason"],
            metadata=row["metadata"] if row["metadata"] else {},
        )


async def save_signals(signals: list[Signal]) -> list[Signal]:
    """Save multiple signals to the database."""
    saved = []
    for signal in signals:
        saved.append(await save_signal(signal))
    return saved


async def get_signal(signal_id: UUID) -> Signal | None:
    """Get a signal by ID."""
    async with get_cursor() as cur:
        await cur.execute(
            """
            SELECT id, time, strategy_id, instrument, signal_type, strength, reason, metadata
            FROM signals
            WHERE id = %s
            """,
            (signal_id,),
        )
        row = await cur.fetchone()

        if not row:
            return None

        return Signal(
            id=row["id"],
            time=row["time"],
            strategy_id=row["strategy_id"],
            instrument=row["instrument"],
            signal_type=SignalType(row["signal_type"]),
            strength=float(row["strength"]) if row["strength"] else None,
            reason=row["reason"],
            metadata=row["metadata"] if row["metadata"] else {},
        )


async def list_signals(
    strategy_id: str | None = None,
    instrument: str | None = None,
    signal_type: SignalType | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Signal]:
    """
    List signals with optional filtering.

    Args:
        strategy_id: Filter by strategy
        instrument: Filter by instrument
        signal_type: Filter by signal type
        start: Start time filter
        end: End time filter
        limit: Maximum results
        offset: Results offset for pagination

    Returns:
        List of matching signals
    """
    conditions = []
    params: list[Any] = []

    if strategy_id:
        conditions.append("strategy_id = %s")
        params.append(strategy_id)

    if instrument:
        conditions.append("instrument = %s")
        params.append(instrument)

    if signal_type:
        conditions.append("signal_type = %s")
        params.append(signal_type.value)

    if start:
        conditions.append("time >= %s")
        params.append(start)

    if end:
        conditions.append("time <= %s")
        params.append(end)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    params.extend([limit, offset])

    async with get_cursor() as cur:
        await cur.execute(
            f"""
            SELECT id, time, strategy_id, instrument, signal_type, strength, reason, metadata
            FROM signals
            WHERE {where_clause}
            ORDER BY time DESC
            LIMIT %s OFFSET %s
            """,
            params,
        )
        rows = await cur.fetchall()

        return [
            Signal(
                id=row["id"],
                time=row["time"],
                strategy_id=row["strategy_id"],
                instrument=row["instrument"],
                signal_type=SignalType(row["signal_type"]),
                strength=float(row["strength"]) if row["strength"] else None,
                reason=row["reason"],
                metadata=row["metadata"] if row["metadata"] else {},
            )
            for row in rows
        ]


async def count_signals(
    strategy_id: str | None = None,
    instrument: str | None = None,
    signal_type: SignalType | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> int:
    """Count signals matching the filters."""
    conditions = []
    params: list[Any] = []

    if strategy_id:
        conditions.append("strategy_id = %s")
        params.append(strategy_id)

    if instrument:
        conditions.append("instrument = %s")
        params.append(instrument)

    if signal_type:
        conditions.append("signal_type = %s")
        params.append(signal_type.value)

    if start:
        conditions.append("time >= %s")
        params.append(start)

    if end:
        conditions.append("time <= %s")
        params.append(end)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    async with get_cursor() as cur:
        await cur.execute(
            f"""
            SELECT COUNT(*) as count
            FROM signals
            WHERE {where_clause}
            """,
            params,
        )
        row = await cur.fetchone()
        return row["count"]


async def get_latest_signals(
    strategy_id: str | None = None,
    limit: int = 10,
) -> list[Signal]:
    """Get the most recent signals."""
    return await list_signals(
        strategy_id=strategy_id,
        limit=limit,
    )


async def get_signals_by_strategy(
    strategy_id: str,
    limit: int = 100,
) -> list[Signal]:
    """Get signals for a specific strategy."""
    return await list_signals(
        strategy_id=strategy_id,
        limit=limit,
    )


async def delete_old_signals(days: int = 30) -> int:
    """
    Delete signals older than specified days.

    Args:
        days: Delete signals older than this many days

    Returns:
        Number of signals deleted
    """
    async with get_cursor() as cur:
        await cur.execute(
            """
            DELETE FROM signals
            WHERE time < NOW() - INTERVAL '%s days'
            """,
            (days,),
        )
        await cur.connection.commit()

        deleted = cur.rowcount
        if deleted > 0:
            logger.info(f"Deleted {deleted} signals older than {days} days")

        return deleted
