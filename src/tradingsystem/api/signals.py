"""Signals API endpoints."""

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from tradingsystem.models.signal import Signal, SignalType
from tradingsystem.services import signal_service

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("", response_model=list[Signal])
async def list_signals(
    strategy_id: str | None = Query(None, description="Filter by strategy"),
    instrument: str | None = Query(None, description="Filter by instrument"),
    signal_type: SignalType | None = Query(None, description="Filter by signal type"),
    start: datetime | None = Query(None, description="Start time filter"),
    end: datetime | None = Query(None, description="End time filter"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Results offset for pagination"),
) -> list[Signal]:
    """
    List signals with optional filtering.

    Supports filtering by strategy, instrument, signal type, and time range.
    Results are ordered by time descending (newest first).
    """
    return await signal_service.list_signals(
        strategy_id=strategy_id,
        instrument=instrument,
        signal_type=signal_type,
        start=start,
        end=end,
        limit=limit,
        offset=offset,
    )


@router.get("/count")
async def count_signals(
    strategy_id: str | None = Query(None, description="Filter by strategy"),
    instrument: str | None = Query(None, description="Filter by instrument"),
    signal_type: SignalType | None = Query(None, description="Filter by signal type"),
    start: datetime | None = Query(None, description="Start time filter"),
    end: datetime | None = Query(None, description="End time filter"),
) -> dict[str, int]:
    """Get count of signals matching filters."""
    count = await signal_service.count_signals(
        strategy_id=strategy_id,
        instrument=instrument,
        signal_type=signal_type,
        start=start,
        end=end,
    )
    return {"count": count}


@router.get("/latest", response_model=list[Signal])
async def get_latest_signals(
    strategy_id: str | None = Query(None, description="Filter by strategy"),
    limit: int = Query(10, ge=1, le=100, description="Number of signals"),
) -> list[Signal]:
    """Get the most recent signals."""
    return await signal_service.get_latest_signals(
        strategy_id=strategy_id,
        limit=limit,
    )


@router.get("/{signal_id}", response_model=Signal)
async def get_signal(signal_id: UUID) -> Signal:
    """Get a signal by ID."""
    signal = await signal_service.get_signal(signal_id)
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")
    return signal


@router.get("/strategy/{strategy_id}", response_model=list[Signal])
async def get_signals_by_strategy(
    strategy_id: str,
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
) -> list[Signal]:
    """Get signals for a specific strategy."""
    return await signal_service.get_signals_by_strategy(
        strategy_id=strategy_id,
        limit=limit,
    )


@router.delete("/cleanup")
async def cleanup_old_signals(
    days: int = Query(30, ge=1, le=365, description="Delete signals older than this many days"),
) -> dict[str, Any]:
    """Delete signals older than specified days."""
    deleted = await signal_service.delete_old_signals(days=days)
    return {
        "status": "success",
        "deleted": deleted,
        "days_threshold": days,
    }
