"""Charts API endpoints."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from tradingsystem.core.rateservice import Candle
from tradingsystem.models.chart import Chart, ChartCreate
from tradingsystem.services import chart_service

router = APIRouter(prefix="/charts", tags=["charts"])


@router.get("", response_model=list[Chart])
async def list_charts() -> list[Chart]:
    """List all configured charts."""
    return await chart_service.list_charts()


@router.post("", response_model=Chart, status_code=201)
async def create_chart(chart: ChartCreate) -> Chart:
    """Create a new chart configuration."""
    return await chart_service.create_chart(chart)


@router.get("/{chart_id}", response_model=Chart)
async def get_chart(chart_id: UUID) -> Chart:
    """Get a chart by ID."""
    chart = await chart_service.get_chart(chart_id)
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")
    return chart


@router.delete("/{chart_id}", status_code=204)
async def delete_chart(chart_id: UUID) -> None:
    """Delete a chart by ID."""
    deleted = await chart_service.delete_chart(chart_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Chart not found")


@router.get("/{chart_id}/candles", response_model=list[Candle])
async def get_chart_candles(
    chart_id: UUID,
    start: datetime | None = Query(None, description="Start time for candles"),
    end: datetime | None = Query(None, description="End time for candles"),
    limit: int = Query(100, ge=1, le=5000, description="Maximum candles to return"),
) -> list[Candle]:
    """Get candles for a chart."""
    chart = await chart_service.get_chart(chart_id)
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")

    return await chart_service.get_chart_candles(
        instrument=chart.instrument,
        period=chart.period,
        start=start,
        end=end,
        limit=limit,
    )


@router.get("/by-instrument/{instrument}", response_model=Chart)
async def get_chart_by_instrument(
    instrument: str,
    period: str = Query("M1", description="Candle period"),
) -> Chart:
    """Get a chart by instrument and period."""
    chart = await chart_service.get_chart_by_instrument_period(instrument, period)
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")
    return chart
