"""Series API endpoints."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from tradingsystem.core.rateservice import Candle
from tradingsystem.models.series import Series, SeriesCreate
from tradingsystem.services import series_service

router = APIRouter(prefix="/series", tags=["series"])


@router.get("", response_model=list[Series])
async def list_series() -> list[Series]:
    """List all configured series."""
    return await series_service.list_series()


@router.post("", response_model=Series, status_code=201)
async def create_series(series: SeriesCreate) -> Series:
    """Create a new series configuration."""
    return await series_service.create_series(series)


@router.get("/{series_id}", response_model=Series)
async def get_series(series_id: UUID) -> Series:
    """Get a series by ID."""
    series = await series_service.get_series(series_id)
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")
    return series


@router.delete("/{series_id}", status_code=204)
async def delete_series(series_id: UUID) -> None:
    """Delete a series by ID."""
    deleted = await series_service.delete_series(series_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Series not found")


@router.get("/{series_id}/candles", response_model=list[Candle])
async def get_series_candles(
    series_id: UUID,
    start: datetime | None = Query(None, description="Start time for candles"),
    end: datetime | None = Query(None, description="End time for candles"),
    limit: int = Query(100, ge=1, le=5000, description="Maximum candles to return"),
) -> list[Candle]:
    """Get candles for a series."""
    series = await series_service.get_series(series_id)
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")

    return await series_service.get_series_candles(
        instrument=series.instrument,
        period=series.period,
        start=start,
        end=end,
        limit=limit,
    )


@router.get("/by-instrument/{instrument}", response_model=Series)
async def get_series_by_instrument(
    instrument: str,
    period: str = Query("M1", description="Candle period"),
) -> Series:
    """
    Get a series by instrument and period.

    If the series doesn't exist, it will be auto-created.
    """
    series = await series_service.get_series_by_instrument_period(instrument, period)
    if not series:
        # Auto-create the series if it doesn't exist
        series = await series_service.create_series(
            SeriesCreate(instrument=instrument, period=period)
        )
    return series
