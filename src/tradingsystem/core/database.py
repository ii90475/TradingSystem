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

            # Migrate old charts schema (instrument, period) → (name, series_id)
            await cur.execute("""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'charts' AND column_name = 'instrument'
                    ) AND NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'charts' AND column_name = 'series_id'
                    ) THEN
                        -- Ensure series exist for all chart instrument+period combos
                        INSERT INTO series (instrument, period)
                        SELECT DISTINCT instrument, period FROM charts
                        ON CONFLICT (instrument, period) DO NOTHING;

                        -- Add new columns
                        ALTER TABLE charts ADD COLUMN name TEXT;
                        ALTER TABLE charts ADD COLUMN series_id UUID;

                        -- Populate from existing data
                        UPDATE charts c
                        SET name = c.instrument || ' · ' || c.period,
                            series_id = s.id
                        FROM series s
                        WHERE s.instrument = c.instrument AND s.period = c.period;

                        -- Set NOT NULL after population
                        ALTER TABLE charts ALTER COLUMN name SET NOT NULL;
                        ALTER TABLE charts ALTER COLUMN series_id SET NOT NULL;

                        -- Add FK constraint
                        ALTER TABLE charts
                            ADD CONSTRAINT fk_charts_series
                            FOREIGN KEY (series_id) REFERENCES series(id) ON DELETE CASCADE;

                        -- Drop old columns
                        ALTER TABLE charts DROP COLUMN instrument;
                        ALTER TABLE charts DROP COLUMN period;

                        RAISE NOTICE 'Migrated charts table to new schema (name, series_id)';
                    END IF;
                END $$;
            """)

            # Charts (named views on a Series)
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS charts (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    name TEXT NOT NULL,
                    series_id UUID NOT NULL REFERENCES series(id) ON DELETE CASCADE,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)

            # Migrate chart_indicators: rename series_id → chart_id
            # (the column already FKs to charts(id), just misnamed)
            await cur.execute("""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'chart_indicators' AND column_name = 'series_id'
                    ) AND NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'chart_indicators' AND column_name = 'chart_id'
                    ) THEN
                        -- Drop old FK constraint
                        ALTER TABLE chart_indicators
                            DROP CONSTRAINT IF EXISTS chart_indicators_chart_id_fkey;

                        -- Rename column
                        ALTER TABLE chart_indicators RENAME COLUMN series_id TO chart_id;

                        -- Re-add FK constraint
                        ALTER TABLE chart_indicators
                            ADD CONSTRAINT fk_chart_indicators_chart
                            FOREIGN KEY (chart_id) REFERENCES charts(id) ON DELETE CASCADE;

                        RAISE NOTICE 'Migrated chart_indicators: renamed series_id → chart_id';
                    END IF;
                END $$;
            """)

            # Indicator configurations per chart
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS chart_indicators (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    chart_id UUID REFERENCES charts(id) ON DELETE CASCADE,
                    indicator_type TEXT NOT NULL,
                    parameters JSONB NOT NULL DEFAULT '{}',
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
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

            # Strategy assignments on charts
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS chart_strategies (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    chart_id UUID NOT NULL REFERENCES charts(id) ON DELETE CASCADE,
                    strategy_id VARCHAR(50) NOT NULL,
                    name TEXT NOT NULL DEFAULT '',
                    parameters JSONB DEFAULT '{}',
                    enabled BOOLEAN DEFAULT false,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)
            # Migration: add name column if missing
            await cur.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'chart_strategies' AND column_name = 'name'
                    ) THEN
                        ALTER TABLE chart_strategies ADD COLUMN name TEXT NOT NULL DEFAULT '';
                        UPDATE chart_strategies SET name = strategy_id WHERE name = '';
                    END IF;
                END $$;
            """)
            await cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_chart_strategies_chart
                ON chart_strategies(chart_id);
            """)
            await cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_chart_strategies_strategy
                ON chart_strategies(strategy_id);
            """)
            await cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_chart_strategies_enabled
                ON chart_strategies(enabled);
            """)

            # Migrate strategy_instances → chart_strategies (one-time)
            await cur.execute("""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_name = 'strategy_instances'
                    ) AND EXISTS (
                        SELECT 1 FROM strategy_instances
                    ) THEN
                        -- For each strategy_instance, find/create matching series and chart,
                        -- then insert into chart_strategies

                        -- Ensure series exist for all instrument+period combos
                        INSERT INTO series (instrument, period)
                        SELECT DISTINCT instrument, period
                        FROM strategy_instances
                        ON CONFLICT (instrument, period) DO NOTHING;

                        -- Ensure charts exist for all series referenced by strategy_instances
                        INSERT INTO charts (name, series_id)
                        SELECT s.instrument || ' · ' || s.period, s.id
                        FROM strategy_instances si
                        JOIN series s ON s.instrument = si.instrument AND s.period = si.period
                        WHERE NOT EXISTS (
                            SELECT 1 FROM charts c WHERE c.series_id = s.id
                        )
                        GROUP BY s.id, s.instrument, s.period;

                        -- Migrate instances to chart_strategies
                        INSERT INTO chart_strategies (id, chart_id, strategy_id, parameters, enabled, created_at, updated_at)
                        SELECT si.id, c.id, si.strategy_id, si.parameters, si.enabled, si.created_at, si.updated_at
                        FROM strategy_instances si
                        JOIN series s ON s.instrument = si.instrument AND s.period = si.period
                        JOIN charts c ON c.series_id = s.id
                        WHERE NOT EXISTS (
                            SELECT 1 FROM chart_strategies cs WHERE cs.id = si.id
                        );

                        -- Drop old table after successful migration
                        DROP TABLE strategy_instances;
                    END IF;
                END $$;
            """)

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
