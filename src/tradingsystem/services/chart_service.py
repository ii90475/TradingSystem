"""Chart service for managing charts and fetching candle data."""

import logging
from datetime import datetime
from uuid import UUID

import pandas as pd

from tradingsystem.core.database import get_cursor
from tradingsystem.core.rateservice import Candle, rateservice_client
from tradingsystem.models.chart import Chart, ChartCreate

logger = logging.getLogger(__name__)


async def create_chart(chart: ChartCreate) -> Chart:
    """
    Create a new chart configuration.

    Args:
        chart: Chart creation request with instrument and period

    Returns:
        Created Chart object
    """
    async with get_cursor() as cur:
        await cur.execute(
            """
            INSERT INTO charts (instrument, period)
            VALUES (%s, %s)
            ON CONFLICT (instrument, period) DO UPDATE SET instrument = EXCLUDED.instrument
            RETURNING id, instrument, period, created_at
            """,
            (chart.instrument, chart.period),
        )
        row = await cur.fetchone()
        await cur.connection.commit()

        logger.info(
            "chart_created",
            extra={
                "event": "chart",
                "action": "create",
                "instrument": chart.instrument,
                "period": chart.period,
                "id": str(row["id"]),
            },
        )

        return Chart(**row)


async def get_chart(chart_id: UUID) -> Chart | None:
    """Get a chart by ID."""
    async with get_cursor() as cur:
        await cur.execute(
            """
            SELECT id, instrument, period, created_at
            FROM charts
            WHERE id = %s
            """,
            (chart_id,),
        )
        row = await cur.fetchone()
        return Chart(**row) if row else None


async def get_chart_by_instrument_period(instrument: str, period: str) -> Chart | None:
    """Get a chart by instrument and period."""
    async with get_cursor() as cur:
        await cur.execute(
            """
            SELECT id, instrument, period, created_at
            FROM charts
            WHERE instrument = %s AND period = %s
            """,
            (instrument, period),
        )
        row = await cur.fetchone()
        return Chart(**row) if row else None


async def list_charts() -> list[Chart]:
    """List all configured charts."""
    async with get_cursor() as cur:
        await cur.execute(
            """
            SELECT id, instrument, period, created_at
            FROM charts
            ORDER BY instrument, period
            """
        )
        rows = await cur.fetchall()
        return [Chart(**row) for row in rows]


async def delete_chart(chart_id: UUID) -> bool:
    """Delete a chart by ID."""
    async with get_cursor() as cur:
        await cur.execute(
            """
            DELETE FROM charts WHERE id = %s
            """,
            (chart_id,),
        )
        await cur.connection.commit()
        return cur.rowcount > 0


async def get_chart_candles(
    instrument: str,
    period: str = "M1",
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 100,
) -> list[Candle]:
    """
    Fetch candles for a chart from RateService.

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


async def get_chart_dataframe(
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
    candles = await get_chart_candles(
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
