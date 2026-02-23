"""Service for managing saved strategy instances.

Provides CRUD operations for StrategyInstance entities and integration
with the backtest system.
"""

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from tradingsystem.core.database import get_connection
from tradingsystem.models.strategy_instance import StrategyInstance
from tradingsystem.strategies.registry import StrategyRegistry

logger = logging.getLogger(__name__)


async def init_strategy_instances_table() -> None:
    """Initialize the strategy_instances table if it doesn't exist."""
    async with get_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS strategy_instances (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    name VARCHAR(100) NOT NULL,
                    strategy_id VARCHAR(50) NOT NULL,
                    instrument VARCHAR(20) NOT NULL,
                    period VARCHAR(10) NOT NULL,
                    parameters JSONB DEFAULT '{}',
                    enabled BOOLEAN DEFAULT true,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(name)
                )
            """)
            await cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_strategy_instances_strategy
                ON strategy_instances(strategy_id)
            """)
            await cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_strategy_instances_instrument
                ON strategy_instances(instrument)
            """)
            await cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_strategy_instances_enabled
                ON strategy_instances(enabled)
            """)
            await conn.commit()
    logger.info("strategy_instances table initialized")


async def create_instance(
    name: str,
    strategy_id: str,
    instrument: str,
    period: str,
    parameters: dict[str, Any] | None = None,
    enabled: bool = True,
) -> StrategyInstance:
    """
    Create a new strategy instance.

    Args:
        name: User-friendly name for this configuration
        strategy_id: ID of the base strategy (e.g., "ma_crossover")
        instrument: Currency pair (e.g., "GBP_USD")
        period: Timeframe (e.g., "D", "H1")
        parameters: Strategy-specific parameters
        enabled: Whether to enable for signal generation

    Returns:
        The created StrategyInstance

    Raises:
        ValueError: If strategy_id doesn't exist or name is duplicate
    """
    # Validate strategy exists
    if not StrategyRegistry.get(strategy_id):
        raise ValueError(f"Unknown strategy: {strategy_id}")

    instance = StrategyInstance.create(
        name=name,
        strategy_id=strategy_id,
        instrument=instrument,
        period=period,
        parameters=parameters,
        enabled=enabled,
    )

    async with get_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO strategy_instances
                    (id, name, strategy_id, instrument, period, parameters, enabled, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    instance.id,
                    instance.name,
                    instance.strategy_id,
                    instance.instrument,
                    instance.period,
                    Jsonb(instance.parameters),
                    instance.enabled,
                    instance.created_at,
                    instance.updated_at,
                ),
            )
            await conn.commit()

    logger.info(f"Created strategy instance: {name} ({strategy_id} on {instrument}/{period})")
    return instance


async def get_instance(instance_id: UUID) -> StrategyInstance | None:
    """Get a strategy instance by ID."""
    async with get_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT id, name, strategy_id, instrument, period, parameters,
                       enabled, created_at, updated_at
                FROM strategy_instances
                WHERE id = %s
                """,
                (instance_id,),
            )
            row = await cur.fetchone()
            if row:
                return StrategyInstance.from_row({
                    "id": row[0],
                    "name": row[1],
                    "strategy_id": row[2],
                    "instrument": row[3],
                    "period": row[4],
                    "parameters": row[5],
                    "enabled": row[6],
                    "created_at": row[7],
                    "updated_at": row[8],
                })
    return None


async def list_instances(
    strategy_id: str | None = None,
    instrument: str | None = None,
    enabled: bool | None = None,
) -> list[StrategyInstance]:
    """
    List strategy instances with optional filters.

    Args:
        strategy_id: Filter by base strategy
        instrument: Filter by instrument
        enabled: Filter by enabled status
    """
    conditions = []
    params = []

    if strategy_id:
        conditions.append("strategy_id = %s")
        params.append(strategy_id)
    if instrument:
        conditions.append("instrument = %s")
        params.append(instrument)
    if enabled is not None:
        conditions.append("enabled = %s")
        params.append(enabled)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    async with get_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                f"""
                SELECT id, name, strategy_id, instrument, period, parameters,
                       enabled, created_at, updated_at
                FROM strategy_instances
                WHERE {where_clause}
                ORDER BY created_at DESC
                """,
                params,
            )
            rows = await cur.fetchall()
            return [
                StrategyInstance.from_row({
                    "id": row[0],
                    "name": row[1],
                    "strategy_id": row[2],
                    "instrument": row[3],
                    "period": row[4],
                    "parameters": row[5],
                    "enabled": row[6],
                    "created_at": row[7],
                    "updated_at": row[8],
                })
                for row in rows
            ]


async def update_instance(
    instance_id: UUID,
    name: str | None = None,
    parameters: dict[str, Any] | None = None,
    enabled: bool | None = None,
) -> StrategyInstance | None:
    """
    Update a strategy instance.

    Note: strategy_id, instrument, and period cannot be changed.
    Create a new instance instead if you need different values.
    """
    updates = []
    params = []

    if name is not None:
        updates.append("name = %s")
        params.append(name)
    if parameters is not None:
        updates.append("parameters = %s")
        params.append(Jsonb(parameters))
    if enabled is not None:
        updates.append("enabled = %s")
        params.append(enabled)

    if not updates:
        return await get_instance(instance_id)

    updates.append("updated_at = %s")
    params.append(datetime.now(timezone.utc))
    params.append(instance_id)

    async with get_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                f"""
                UPDATE strategy_instances
                SET {", ".join(updates)}
                WHERE id = %s
                """,
                params,
            )
            await conn.commit()

    return await get_instance(instance_id)


async def delete_instance(instance_id: UUID) -> bool:
    """Delete a strategy instance."""
    async with get_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM strategy_instances WHERE id = %s",
                (instance_id,),
            )
            await conn.commit()
            deleted = cur.rowcount > 0

    if deleted:
        logger.info(f"Deleted strategy instance: {instance_id}")
    return deleted


async def toggle_enabled(instance_id: UUID) -> StrategyInstance | None:
    """Toggle the enabled status of a strategy instance."""
    instance = await get_instance(instance_id)
    if not instance:
        return None

    return await update_instance(instance_id, enabled=not instance.enabled)


async def get_instances_for_instrument(
    instrument: str,
    enabled_only: bool = True,
) -> list[StrategyInstance]:
    """Get all strategy instances configured for a specific instrument."""
    return await list_instances(
        instrument=instrument,
        enabled=True if enabled_only else None,
    )
