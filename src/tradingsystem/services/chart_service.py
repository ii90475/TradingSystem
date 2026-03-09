"""Chart service for managing named chart views on series."""

import logging
from uuid import UUID

from tradingsystem.core.database import get_cursor
from tradingsystem.models.chart import Chart, ChartCreate, ChartDetail

logger = logging.getLogger(__name__)


async def create_chart(chart: ChartCreate) -> Chart:
    """Create a new chart linked to a series."""
    async with get_cursor() as cur:
        await cur.execute(
            """
            INSERT INTO charts (name, series_id)
            VALUES (%s, %s)
            RETURNING id, name, series_id, created_at
            """,
            (chart.name, chart.series_id),
        )
        row = await cur.fetchone()
        await cur.connection.commit()

        logger.info(
            "chart_created",
            extra={
                "event": "chart",
                "action": "create",
                "name": chart.name,
                "series_id": str(chart.series_id),
                "id": str(row["id"]),
            },
        )

        return Chart(**row)


async def get_chart(chart_id: UUID) -> Chart | None:
    """Get a chart by ID."""
    async with get_cursor() as cur:
        await cur.execute(
            """
            SELECT id, name, series_id, created_at
            FROM charts
            WHERE id = %s
            """,
            (chart_id,),
        )
        row = await cur.fetchone()
        return Chart(**row) if row else None


async def list_charts() -> list[ChartDetail]:
    """List all charts with series instrument and period."""
    async with get_cursor() as cur:
        await cur.execute(
            """
            SELECT c.id, c.name, c.series_id, s.instrument, s.period, c.created_at
            FROM charts c
            JOIN series s ON c.series_id = s.id
            ORDER BY c.created_at
            """
        )
        rows = await cur.fetchall()
        return [ChartDetail(**row) for row in rows]


async def list_charts_for_series(series_id: UUID) -> list[Chart]:
    """List all charts for a given series."""
    async with get_cursor() as cur:
        await cur.execute(
            """
            SELECT id, name, series_id, created_at
            FROM charts
            WHERE series_id = %s
            ORDER BY created_at
            """,
            (series_id,),
        )
        rows = await cur.fetchall()
        return [Chart(**row) for row in rows]


async def update_chart(chart_id: UUID, name: str) -> Chart | None:
    """Update a chart's name."""
    async with get_cursor() as cur:
        await cur.execute(
            """
            UPDATE charts SET name = %s
            WHERE id = %s
            RETURNING id, name, series_id, created_at
            """,
            (name, chart_id),
        )
        row = await cur.fetchone()
        await cur.connection.commit()
        return Chart(**row) if row else None


async def delete_chart(chart_id: UUID) -> bool:
    """Delete a chart by ID."""
    async with get_cursor() as cur:
        await cur.execute(
            "DELETE FROM charts WHERE id = %s",
            (chart_id,),
        )
        await cur.connection.commit()
        return cur.rowcount > 0
