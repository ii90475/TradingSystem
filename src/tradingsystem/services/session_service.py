"""
Service for managing chart session persistence.

This module provides database operations for saving and retrieving chart
session state. Sessions are stored in the chart_sessions table with JSONB
for the indicators array, allowing flexible schema evolution.

Architecture:
    - Sessions are keyed by session_key (default: "default")
    - Upsert semantics: save creates or updates as needed
    - Indicators stored as JSONB for flexible nested data
    - Auto-creates table on startup if not exists

Database Schema:
    chart_sessions:
        id UUID PRIMARY KEY
        session_key VARCHAR(255) UNIQUE - session identifier
        instrument VARCHAR(20) - currency pair (e.g., 'EUR_USD')
        period VARCHAR(10) - timeframe (e.g., 'M5', 'H1')
        indicators JSONB - array of indicator configs
        updated_at TIMESTAMPTZ - last modification time
"""

import json
import logging
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from psycopg.rows import dict_row

from tradingsystem.core.database import get_connection, get_cursor
from tradingsystem.models.session import ChartSession, ChartSessionUpdate, IndicatorConfig

logger = logging.getLogger(__name__)

# SQL for session table - uses IF NOT EXISTS for idempotent initialization
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS chart_sessions (
    id UUID PRIMARY KEY,
    session_key VARCHAR(255) NOT NULL UNIQUE,
    instrument VARCHAR(20) NOT NULL DEFAULT 'EUR_USD',
    period VARCHAR(10) NOT NULL DEFAULT 'M5',
    indicators JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_chart_sessions_key ON chart_sessions(session_key);
"""


async def init_session_table() -> None:
    """
    Create the chart_sessions table if it doesn't exist.

    Called during application startup. Safe to call multiple times due to
    IF NOT EXISTS clauses. Creates both the table and an index on session_key.
    """
    async with get_connection() as conn:
        await conn.execute(CREATE_TABLE_SQL)
        await conn.commit()
    logger.info("Chart sessions table initialized")


async def get_session(session_key: str = "default") -> ChartSession | None:
    """
    Get a chart session by key.

    Retrieves the saved session state from the database. Returns None if
    no session exists, allowing the frontend to fall back to defaults.

    Args:
        session_key: Session identifier (default: "default")

    Returns:
        ChartSession if found, None otherwise
    """
    async with get_cursor() as cur:
        await cur.execute(
            """
            SELECT id, session_key, instrument, period, indicators, updated_at
            FROM chart_sessions
            WHERE session_key = %s
            """,
            (session_key,),
        )
        row = await cur.fetchone()
        if not row:
            return None

        # Parse JSONB indicators array into IndicatorConfig objects
        return ChartSession(
            id=row["id"],
            session_key=row["session_key"],
            instrument=row["instrument"],
            period=row["period"],
            indicators=[IndicatorConfig(**ind) for ind in row["indicators"]],
            updated_at=row["updated_at"],
        )


async def save_session(session_key: str, update: ChartSessionUpdate) -> ChartSession:
    """
    Save or update a chart session.

    Uses PostgreSQL upsert (INSERT ... ON CONFLICT DO UPDATE) to either
    create a new session or update an existing one atomically.

    The indicators list is serialized to JSONB, preserving the full
    configuration for each indicator including params and display settings.

    Args:
        session_key: Session identifier (default: "default")
        update: Session data to save (instrument, period, indicators)

    Returns:
        The saved ChartSession with updated timestamp
    """
    # Convert Pydantic models to JSON-serializable dicts
    indicators_json = []
    if update.indicators:
        indicators_json = [ind.model_dump() for ind in update.indicators]

    async with get_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            # Upsert: insert new or update existing session
            await cur.execute(
                """
                INSERT INTO chart_sessions (id, session_key, instrument, period, indicators, updated_at)
                VALUES (%s, %s, %s, %s, %s::jsonb, NOW())
                ON CONFLICT (session_key) DO UPDATE SET
                    instrument = COALESCE(EXCLUDED.instrument, chart_sessions.instrument),
                    period = COALESCE(EXCLUDED.period, chart_sessions.period),
                    indicators = COALESCE(EXCLUDED.indicators, chart_sessions.indicators),
                    updated_at = NOW()
                RETURNING id, session_key, instrument, period, indicators, updated_at
                """,
                (
                    uuid4(),
                    session_key,
                    update.instrument or "EUR_USD",
                    update.period or "M5",
                    json.dumps(indicators_json),
                ),
            )
            row = await cur.fetchone()
        await conn.commit()

        return ChartSession(
            id=row["id"],
            session_key=row["session_key"],
            instrument=row["instrument"],
            period=row["period"],
            indicators=[IndicatorConfig(**ind) for ind in row["indicators"]],
            updated_at=row["updated_at"],
        )


async def delete_session(session_key: str = "default") -> bool:
    """
    Delete a chart session.

    Removes the session from the database. The frontend should revert to
    default settings when no session exists.

    Args:
        session_key: Session identifier (default: "default")

    Returns:
        True if a session was deleted, False if none existed
    """
    async with get_connection() as conn:
        cur = await conn.execute(
            "DELETE FROM chart_sessions WHERE session_key = %s",
            (session_key,),
        )
        deleted = cur.rowcount > 0
        await conn.commit()
        return deleted
