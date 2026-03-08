"""Indicators API endpoints."""

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from tradingsystem.models.series import SeriesIndicator, SeriesIndicatorCreate
from tradingsystem.services import series_service, indicator_service

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


# Series-indicator endpoints
@router.get("/series/{series_id}", response_model=list[SeriesIndicator])
async def get_series_indicators(series_id: UUID) -> list[SeriesIndicator]:
    """Get all indicators configured for a series."""
    series = await series_service.get_series(series_id)
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")

    return await indicator_service.get_series_indicators(series_id)


@router.post("/series/{series_id}", response_model=SeriesIndicator, status_code=201)
async def add_indicator_to_series(
    series_id: UUID,
    indicator: SeriesIndicatorCreate,
) -> SeriesIndicator:
    """Add an indicator to a series configuration."""
    series = await series_service.get_series(series_id)
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")

    try:
        return await indicator_service.add_indicator_to_series(series_id, indicator)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/series-indicator/{indicator_id}", status_code=204)
async def delete_series_indicator(indicator_id: UUID) -> None:
    """Delete an indicator from a series."""
    deleted = await indicator_service.delete_series_indicator(indicator_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Indicator not found")
