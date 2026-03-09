"""Charts API endpoints."""

from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from tradingsystem.models.chart import Chart, ChartCreate, ChartDetail
from tradingsystem.services import chart_service, series_service

router = APIRouter(prefix="/charts", tags=["charts"])


class ChartUpdate(BaseModel):
    """Request model for updating a chart."""

    name: str


@router.get("", response_model=list[ChartDetail])
async def list_charts() -> list[ChartDetail]:
    """List all charts with series info."""
    return await chart_service.list_charts()


@router.post("", response_model=Chart, status_code=201)
async def create_chart(chart: ChartCreate) -> Chart:
    """Create a new chart linked to a series."""
    series = await series_service.get_series(chart.series_id)
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")

    return await chart_service.create_chart(chart)


@router.get("/{chart_id}", response_model=Chart)
async def get_chart(chart_id: UUID) -> Chart:
    """Get a chart by ID."""
    chart = await chart_service.get_chart(chart_id)
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")
    return chart


@router.patch("/{chart_id}", response_model=Chart)
async def update_chart(chart_id: UUID, update: ChartUpdate) -> Chart:
    """Update a chart's name."""
    chart = await chart_service.update_chart(chart_id, update.name)
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")
    return chart


@router.delete("/{chart_id}", status_code=204)
async def delete_chart(chart_id: UUID) -> None:
    """Delete a chart."""
    deleted = await chart_service.delete_chart(chart_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Chart not found")


@router.get("/series/{series_id}", response_model=list[Chart])
async def list_charts_for_series(series_id: UUID) -> list[Chart]:
    """List all charts for a series."""
    series = await series_service.get_series(series_id)
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")

    return await chart_service.list_charts_for_series(series_id)
