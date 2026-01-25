"""Backtest API endpoints."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from tradingsystem.models.backtest import (
    BacktestRequest,
    BacktestResult,
    BacktestSummary,
)
from tradingsystem.services import backtest_service

router = APIRouter(prefix="/backtest", tags=["backtest"])


@router.post("", response_model=BacktestResult)
async def run_backtest(request: BacktestRequest) -> BacktestResult:
    """
    Run a backtest for a strategy.

    Executes the strategy against historical data and returns
    performance metrics, trades, and equity curve.
    """
    try:
        result = await backtest_service.run_backtest(request)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backtest failed: {e}")


@router.get("/history", response_model=list[BacktestSummary])
async def list_backtests(
    strategy_id: str | None = Query(None, description="Filter by strategy"),
    instrument: str | None = Query(None, description="Filter by instrument"),
    limit: int = Query(50, ge=1, le=200, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Results offset"),
) -> list[BacktestSummary]:
    """List past backtest runs with optional filtering."""
    return await backtest_service.list_backtests(
        strategy_id=strategy_id,
        instrument=instrument,
        limit=limit,
        offset=offset,
    )


@router.get("/{backtest_id}", response_model=BacktestResult)
async def get_backtest(backtest_id: UUID) -> BacktestResult:
    """Get detailed backtest results by ID."""
    result = await backtest_service.get_backtest(backtest_id)
    if not result:
        raise HTTPException(status_code=404, detail="Backtest not found")
    return result


@router.delete("/{backtest_id}", status_code=204)
async def delete_backtest(backtest_id: UUID) -> None:
    """Delete a backtest result."""
    deleted = await backtest_service.delete_backtest(backtest_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Backtest not found")


@router.get("/{backtest_id}/trades")
async def get_backtest_trades(backtest_id: UUID) -> list[dict[str, Any]]:
    """Get trades from a backtest."""
    result = await backtest_service.get_backtest(backtest_id)
    if not result:
        raise HTTPException(status_code=404, detail="Backtest not found")

    return [t.model_dump(mode="json") for t in result.trades]


@router.get("/{backtest_id}/equity-curve")
async def get_backtest_equity_curve(backtest_id: UUID) -> list[dict[str, Any]]:
    """Get equity curve from a backtest."""
    result = await backtest_service.get_backtest(backtest_id)
    if not result:
        raise HTTPException(status_code=404, detail="Backtest not found")

    return [e.model_dump(mode="json") for e in result.equity_curve]


@router.get("/{backtest_id}/metrics")
async def get_backtest_metrics(backtest_id: UUID) -> dict[str, Any]:
    """Get performance metrics from a backtest."""
    result = await backtest_service.get_backtest(backtest_id)
    if not result:
        raise HTTPException(status_code=404, detail="Backtest not found")

    return result.metrics.model_dump(mode="json")
