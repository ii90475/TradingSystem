"""Database connection and schema management."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from tradingsystem.core.config import settings

logger = logging.getLogger(__name__)

pool: AsyncConnectionPool | None = None


async def init_pool() -> None:
    """Initialize the database connection pool."""
    global pool
    pool = AsyncConnectionPool(
        conninfo=settings.database_url,
        min_size=2,
        max_size=10,
        open=False,
    )
    await pool.open()


async def close_pool() -> None:
    """Close the database connection pool."""
    global pool
    if pool:
        await pool.close()
        pool = None


@asynccontextmanager
async def get_connection() -> AsyncGenerator[psycopg.AsyncConnection, None]:
    """Get a database connection from the pool."""
    if pool is None:
        raise RuntimeError("Database pool not initialized")
    async with pool.connection() as conn:
        yield conn


@asynccontextmanager
async def get_cursor() -> AsyncGenerator[psycopg.AsyncCursor, None]:
    """Get a database cursor with dict rows."""
    async with get_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            yield cur


async def check_database_health() -> dict:
    """
    Verify database connectivity and pool health.

    Returns:
        Dict with health status, pool stats, and any errors.
    """
    try:
        async with get_cursor() as cur:
            await cur.execute("SELECT 1")
            await cur.fetchone()

        pool_stats = {}
        if pool:
            pool_stats = {
                "min_size": pool.min_size,
                "max_size": pool.max_size,
                "size": pool.get_stats().get("pool_size", 0),
                "available": pool.get_stats().get("pool_available", 0),
                "requests_waiting": pool.get_stats().get("requests_waiting", 0),
            }

        return {
            "healthy": True,
            "pool": pool_stats,
            "error": None,
        }
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {
            "healthy": False,
            "pool": {},
            "error": str(e),
        }


async def init_schema() -> None:
    """Initialize the database schema for TradingSystem."""
    async with get_connection() as conn:
        async with conn.cursor() as cur:
            # Series (instrument + period OHLCV data streams)
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS series (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    instrument TEXT NOT NULL,
                    period TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(instrument, period)
                );
            """)

            # Migrate from charts to series if charts table exists
            await cur.execute("""
                DO $$
                BEGIN
                    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'charts') THEN
                        INSERT INTO series (id, instrument, period, created_at)
                        SELECT id, instrument, period, created_at FROM charts
                        ON CONFLICT (instrument, period) DO NOTHING;
                    END IF;
                END $$;
            """)

            # Indicator configurations per series
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS chart_indicators (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    series_id UUID REFERENCES series(id) ON DELETE CASCADE,
                    indicator_type TEXT NOT NULL,
                    parameters JSONB NOT NULL DEFAULT '{}',
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)

            # Migrate chart_id -> series_id if old column exists
            await cur.execute("""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'chart_indicators' AND column_name = 'chart_id'
                    ) THEN
                        ALTER TABLE chart_indicators RENAME COLUMN chart_id TO series_id;
                    END IF;
                END $$;
            """)

            # Calculated indicator values (hypertable)
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS indicator_values (
                    time TIMESTAMPTZ NOT NULL,
                    chart_indicator_id UUID NOT NULL,
                    value JSONB NOT NULL,
                    PRIMARY KEY (time, chart_indicator_id)
                );
            """)

            # Check if indicator_values is already a hypertable
            await cur.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM timescaledb_information.hypertables
                    WHERE hypertable_name = 'indicator_values'
                );
            """)
            result = await cur.fetchone()
            is_hypertable = result[0] if result else False

            if not is_hypertable:
                try:
                    await cur.execute(
                        "SELECT create_hypertable('indicator_values', 'time', if_not_exists => TRUE);"
                    )
                except Exception as e:
                    logger.warning(f"Could not create hypertable for indicator_values: {e}")

            # Signals generated by strategies
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    time TIMESTAMPTZ NOT NULL,
                    strategy_id TEXT NOT NULL,
                    instrument TEXT NOT NULL,
                    signal_type TEXT NOT NULL,
                    strength NUMERIC(5,4),
                    reason TEXT,
                    metadata JSONB
                );
            """)
            await cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_signals_time ON signals(time DESC);
            """)
            await cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_signals_strategy ON signals(strategy_id, time DESC);
            """)

            # Orders
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    external_id TEXT,
                    strategy_id TEXT,
                    instrument TEXT NOT NULL,
                    side TEXT NOT NULL,
                    order_type TEXT NOT NULL,
                    quantity NUMERIC(12,2) NOT NULL,
                    price NUMERIC(10,5),
                    status TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    filled_at TIMESTAMPTZ,
                    filled_price NUMERIC(10,5),
                    filled_quantity NUMERIC(12,2)
                );
            """)

            # Positions
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS positions (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    instrument TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity NUMERIC(12,2) NOT NULL,
                    entry_price NUMERIC(10,5) NOT NULL,
                    entry_time TIMESTAMPTZ NOT NULL,
                    exit_price NUMERIC(10,5),
                    exit_time TIMESTAMPTZ,
                    status TEXT NOT NULL,
                    strategy_id TEXT,
                    pnl NUMERIC(12,2),
                    pnl_percent NUMERIC(8,4)
                );
            """)
            await cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status, instrument);
            """)

            # Strategy runs (for backtesting & live)
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS strategy_runs (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    strategy_id TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    started_at TIMESTAMPTZ DEFAULT NOW(),
                    ended_at TIMESTAMPTZ,
                    config JSONB,
                    results JSONB
                );
            """)

            await conn.commit()
            logger.info("TradingSystem database schema initialized")
