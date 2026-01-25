"""Indicators API endpoints."""

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from tradingsystem.models.chart import ChartIndicator, ChartIndicatorCreate
from tradingsystem.services import chart_service, indicator_service

router = APIRouter(prefix="/indicators", tags=["indicators"])


class IndicatorCalculation(BaseModel):
    """Request model for indicator calculation."""

    indicator_type: str
    params: dict[str, Any] = {}


class IndicatorResult(BaseModel):
    """Response model for calculated indicator values."""

    indicator: str
    params: dict[str, Any]
    values: list[dict[str, Any]]


@router.get("/available")
async def list_available_indicators() -> dict[str, list[dict[str, Any]]]:
    """List all available indicators (custom and pandas-ta)."""
    return indicator_service.list_available_indicators()


@router.get("/info/{name}")
async def get_indicator_info(name: str) -> dict[str, Any]:
    """Get information about a specific indicator."""
    info = indicator_service.get_indicator_info(name)
    if not info:
        raise HTTPException(status_code=404, detail=f"Indicator not found: {name}")
    return info


@router.post("/calculate", response_model=IndicatorResult)
async def calculate_indicator(
    instrument: str = Query(..., description="Currency pair (e.g., EUR_USD)"),
    period: str = Query("M1", description="Candle period"),
    indicator_type: str = Query(..., description="Indicator name"),
    limit: int = Query(100, ge=1, le=5000, description="Number of candles"),
    start: datetime | None = Query(None, description="Start time"),
    end: datetime | None = Query(None, description="End time"),
    params: str | None = Query(None, description="JSON params (e.g., '{\"length\": 14}')"),
) -> IndicatorResult:
    """
    Calculate an indicator on candle data.

    Pass indicator parameters as a JSON string in the params query parameter.
    """
    import json

    indicator_params = {}
    if params:
        try:
            indicator_params = json.loads(params)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON in params")

    try:
        result = await indicator_service.calculate_indicator(
            instrument=instrument,
            period=period,
            indicator_type=indicator_type,
            params=indicator_params,
            start=start,
            end=end,
            limit=limit,
        )
        return IndicatorResult(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# Chart-indicator endpoints
@router.get("/chart/{chart_id}", response_model=list[ChartIndicator])
async def get_chart_indicators(chart_id: UUID) -> list[ChartIndicator]:
    """Get all indicators configured for a chart."""
    chart = await chart_service.get_chart(chart_id)
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")

    return await indicator_service.get_chart_indicators(chart_id)


@router.post("/chart/{chart_id}", response_model=ChartIndicator, status_code=201)
async def add_indicator_to_chart(
    chart_id: UUID,
    indicator: ChartIndicatorCreate,
) -> ChartIndicator:
    """Add an indicator to a chart configuration."""
    chart = await chart_service.get_chart(chart_id)
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")

    try:
        return await indicator_service.add_indicator_to_chart(chart_id, indicator)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/chart-indicator/{indicator_id}", status_code=204)
async def delete_chart_indicator(indicator_id: UUID) -> None:
    """Delete an indicator from a chart."""
    deleted = await indicator_service.delete_chart_indicator(indicator_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Indicator not found")
