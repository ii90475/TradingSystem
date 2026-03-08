"""Service for managing chart strategy assignments.

Provides CRUD operations for ChartStrategy entities — strategies bound
to charts with parameters and toggle state.
"""

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from tradingsystem.core.database import get_cursor
from tradingsystem.models.chart_strategy import ChartStrategy
from tradingsystem.strategies.registry import StrategyRegistry

logger = logging.getLogger(__name__)


async def create_chart_strategy(
    chart_id: UUID,
    strategy_id: str,
    parameters: dict[str, Any] | None = None,
    enabled: bool = False,
) -> ChartStrategy:
    """
    Create a new chart strategy assignment.

    Raises:
        ValueError: If strategy_id doesn't exist in registry.
    """
    if not StrategyRegistry.get(strategy_id):
        raise ValueError(f"Unknown strategy: {strategy_id}")

    cs = ChartStrategy.create(
        chart_id=chart_id,
        strategy_id=strategy_id,
        parameters=parameters,
        enabled=enabled,
    )

    async with get_cursor() as cur:
        await cur.execute(
            """
            INSERT INTO chart_strategies
                (id, chart_id, strategy_id, parameters, enabled, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (cs.id, cs.chart_id, cs.strategy_id, Jsonb(cs.parameters),
             cs.enabled, cs.created_at, cs.updated_at),
        )
        await cur.connection.commit()

    logger.info(f"Created chart strategy: {strategy_id} on chart {chart_id}")
    return cs


async def get_chart_strategy(cs_id: UUID) -> ChartStrategy | None:
    """Get a chart strategy by ID."""
    async with get_cursor() as cur:
        await cur.execute(
            """
            SELECT id, chart_id, strategy_id, parameters, enabled, created_at, updated_at
            FROM chart_strategies
            WHERE id = %s
            """,
            (cs_id,),
        )
        row = await cur.fetchone()
        return ChartStrategy.from_row(row) if row else None


async def list_chart_strategies(
    chart_id: UUID | None = None,
    strategy_id: str | None = None,
    enabled: bool | None = None,
) -> list[ChartStrategy]:
    """List chart strategies with optional filters."""
    conditions = []
    params = []

    if chart_id is not None:
        conditions.append("chart_id = %s")
        params.append(chart_id)
    if strategy_id is not None:
        conditions.append("strategy_id = %s")
        params.append(strategy_id)
    if enabled is not None:
        conditions.append("enabled = %s")
        params.append(enabled)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    async with get_cursor() as cur:
        await cur.execute(
            f"""
            SELECT id, chart_id, strategy_id, parameters, enabled, created_at, updated_at
            FROM chart_strategies
            WHERE {where_clause}
            ORDER BY created_at DESC
            """,
            params,
        )
        rows = await cur.fetchall()
        return [ChartStrategy.from_row(row) for row in rows]


async def update_chart_strategy(
    cs_id: UUID,
    parameters: dict[str, Any] | None = None,
    enabled: bool | None = None,
) -> ChartStrategy | None:
    """Update a chart strategy's parameters or enabled state."""
    updates = []
    params = []

    if parameters is not None:
        updates.append("parameters = %s")
        params.append(Jsonb(parameters))
    if enabled is not None:
        updates.append("enabled = %s")
        params.append(enabled)

    if not updates:
        return await get_chart_strategy(cs_id)

    updates.append("updated_at = %s")
    params.append(datetime.now(timezone.utc))
    params.append(cs_id)

    async with get_cursor() as cur:
        await cur.execute(
            f"""
            UPDATE chart_strategies
            SET {", ".join(updates)}
            WHERE id = %s
            RETURNING id, chart_id, strategy_id, parameters, enabled, created_at, updated_at
            """,
            params,
        )
        row = await cur.fetchone()
        await cur.connection.commit()
        return ChartStrategy.from_row(row) if row else None


async def delete_chart_strategy(cs_id: UUID) -> bool:
    """Delete a chart strategy."""
    async with get_cursor() as cur:
        await cur.execute(
            "DELETE FROM chart_strategies WHERE id = %s",
            (cs_id,),
        )
        await cur.connection.commit()
        deleted = cur.rowcount > 0

    if deleted:
        logger.info(f"Deleted chart strategy: {cs_id}")
    return deleted


async def toggle_enabled(cs_id: UUID) -> ChartStrategy | None:
    """Toggle the enabled status of a chart strategy."""
    cs = await get_chart_strategy(cs_id)
    if not cs:
        return None
    return await update_chart_strategy(cs_id, enabled=not cs.enabled)
