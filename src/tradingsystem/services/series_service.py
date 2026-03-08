"""Series service for managing series and fetching candle data."""

import logging
from datetime import datetime
from uuid import UUID

import pandas as pd

from tradingsystem.core.database import get_cursor
from tradingsystem.core.rateservice import Candle, rateservice_client
from tradingsystem.models.series import Series, SeriesCreate

logger = logging.getLogger(__name__)


async def create_series(series: SeriesCreate) -> Series:
    """
    Create a new series configuration.

    Args:
        series: Series creation request with instrument and period

    Returns:
        Created Series object
    """
    async with get_cursor() as cur:
        await cur.execute(
            """
            INSERT INTO series (instrument, period)
            VALUES (%s, %s)
            ON CONFLICT (instrument, period) DO UPDATE SET instrument = EXCLUDED.instrument
            RETURNING id, instrument, period, created_at
            """,
            (series.instrument, series.period),
        )
        row = await cur.fetchone()
        await cur.connection.commit()

        logger.info(
            "series_created",
            extra={
                "event": "series",
                "action": "create",
                "instrument": series.instrument,
                "period": series.period,
                "id": str(row["id"]),
            },
        )

        return Series(**row)


async def get_series(series_id: UUID) -> Series | None:
    """Get a series by ID."""
    async with get_cursor() as cur:
        await cur.execute(
            """
            SELECT id, instrument, period, created_at
            FROM series
            WHERE id = %s
            """,
            (series_id,),
        )
        row = await cur.fetchone()
        return Series(**row) if row else None


async def get_series_by_instrument_period(instrument: str, period: str) -> Series | None:
    """Get a series by instrument and period."""
    async with get_cursor() as cur:
        await cur.execute(
            """
            SELECT id, instrument, period, created_at
            FROM series
            WHERE instrument = %s AND period = %s
            """,
            (instrument, period),
        )
        row = await cur.fetchone()
        return Series(**row) if row else None


async def list_series() -> list[Series]:
    """List all configured series."""
    async with get_cursor() as cur:
        await cur.execute(
            """
            SELECT id, instrument, period, created_at
            FROM series
            ORDER BY instrument, period
            """
        )
        rows = await cur.fetchall()
        return [Series(**row) for row in rows]


async def delete_series(series_id: UUID) -> bool:
    """Delete a series by ID."""
    async with get_cursor() as cur:
        await cur.execute(
            """
            DELETE FROM series WHERE id = %s
            """,
            (series_id,),
        )
        await cur.connection.commit()
        return cur.rowcount > 0


async def get_series_candles(
    instrument: str,
    period: str = "M1",
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 100,
) -> list[Candle]:
    """
    Fetch candles for a series from RateService.

    Args:
        instrument: Currency pair (e.g., "EUR_USD")
        period: Candle period (M1, 5m, 15m, 30m, 1h, 4h, 1d)
        start: Start time for history
        end: End time for history
        limit: Maximum number of candles

    Returns:
        List of Candle objects
    """
    return await rateservice_client.get_candles(
        pair=instrument,
        period=period,
        start=start,
        end=end,
        limit=limit,
    )


async def get_series_dataframe(
    instrument: str,
    period: str = "M1",
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 100,
) -> pd.DataFrame:
    """
    Fetch candles and return as a pandas DataFrame for indicator calculation.

    Args:
        instrument: Currency pair (e.g., "EUR_USD")
        period: Candle period
        start: Start time
        end: End time
        limit: Maximum candles

    Returns:
        DataFrame with columns: time, open, high, low, close, volume
    """
    candles = await get_series_candles(
        instrument=instrument,
        period=period,
        start=start,
        end=end,
        limit=limit,
    )

    if not candles:
        return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])

    # Convert to DataFrame
    data = [
        {
            "time": c.time,
            "open": float(c.open),
            "high": float(c.high),
            "low": float(c.low),
            "close": float(c.close),
            "volume": c.volume,
        }
        for c in candles
    ]

    df = pd.DataFrame(data)
    df.set_index("time", inplace=True)
    df.sort_index(inplace=True)

    return df
