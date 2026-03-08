"""API endpoints for chart strategy management."""

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from tradingsystem.services import chart_strategy_service
from tradingsystem.services.chart_service import get_chart
from tradingsystem.services.backtest_service import run_backtest
from tradingsystem.models.backtest import BacktestRequest
from tradingsystem.services.series_service import get_series
from tradingsystem.strategies.registry import StrategyRegistry

router = APIRouter(prefix="/chart-strategies", tags=["Chart Strategies"])


class CreateChartStrategyRequest(BaseModel):
    """Request body for creating a chart strategy."""

    chart_id: UUID = Field(..., description="Chart to attach strategy to")
    strategy_id: str = Field(..., description="Base strategy ID (e.g., 'ma_crossover')")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Strategy parameters")
    enabled: bool = Field(default=False, description="Enable for signal generation")


class UpdateChartStrategyRequest(BaseModel):
    """Request body for updating a chart strategy."""

    parameters: dict[str, Any] | None = None
    enabled: bool | None = None


class ChartStrategyResponse(BaseModel):
    """Response model for a chart strategy."""

    id: str
    chart_id: str
    strategy_id: str
    parameters: dict[str, Any]
    enabled: bool
    created_at: str
    updated_at: str


@router.post("", response_model=ChartStrategyResponse, status_code=201)
async def create_chart_strategy(request: CreateChartStrategyRequest) -> dict[str, Any]:
    """Create a new strategy assignment on a chart."""
    # Verify chart exists
    chart = await get_chart(request.chart_id)
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")

    try:
        cs = await chart_strategy_service.create_chart_strategy(
            chart_id=request.chart_id,
            strategy_id=request.strategy_id,
            parameters=request.parameters,
            enabled=request.enabled,
        )
        return cs.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=list[ChartStrategyResponse])
async def list_chart_strategies(
    chart_id: UUID | None = None,
    strategy_id: str | None = None,
    enabled: bool | None = None,
) -> list[dict[str, Any]]:
    """List chart strategies with optional filters."""
    results = await chart_strategy_service.list_chart_strategies(
        chart_id=chart_id,
        strategy_id=strategy_id,
        enabled=enabled,
    )
    return [cs.to_dict() for cs in results]


@router.get("/strategies")
async def list_available_strategies() -> list[dict[str, Any]]:
    """List all available base strategies that can be used."""
    return StrategyRegistry.list_all()


@router.get("/{cs_id}", response_model=ChartStrategyResponse)
async def get_chart_strategy(cs_id: UUID) -> dict[str, Any]:
    """Get a chart strategy by ID."""
    cs = await chart_strategy_service.get_chart_strategy(cs_id)
    if not cs:
        raise HTTPException(status_code=404, detail="Chart strategy not found")
    return cs.to_dict()


@router.put("/{cs_id}", response_model=ChartStrategyResponse)
async def update_chart_strategy(cs_id: UUID, request: UpdateChartStrategyRequest) -> dict[str, Any]:
    """Update a chart strategy's parameters or enabled state."""
    cs = await chart_strategy_service.update_chart_strategy(
        cs_id=cs_id,
        parameters=request.parameters,
        enabled=request.enabled,
    )
    if not cs:
        raise HTTPException(status_code=404, detail="Chart strategy not found")
    return cs.to_dict()


@router.delete("/{cs_id}", status_code=204)
async def delete_chart_strategy(cs_id: UUID) -> None:
    """Delete a chart strategy."""
    deleted = await chart_strategy_service.delete_chart_strategy(cs_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Chart strategy not found")


@router.patch("/{cs_id}/toggle", response_model=ChartStrategyResponse)
async def toggle_chart_strategy(cs_id: UUID) -> dict[str, Any]:
    """Toggle the enabled status of a chart strategy."""
    cs = await chart_strategy_service.toggle_enabled(cs_id)
    if not cs:
        raise HTTPException(status_code=404, detail="Chart strategy not found")
    return cs.to_dict()


@router.post("/{cs_id}/backtest")
async def run_chart_strategy_backtest(
    cs_id: UUID,
    days: int = 30,
) -> dict[str, Any]:
    """Run a backtest using this chart strategy's configuration."""
    cs = await chart_strategy_service.get_chart_strategy(cs_id)
    if not cs:
        raise HTTPException(status_code=404, detail="Chart strategy not found")

    # Resolve chart → series → instrument + period
    chart = await get_chart(cs.chart_id)
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")

    series = await get_series(chart.series_id)
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")

    try:
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)

        request = BacktestRequest(
            strategy_id=cs.strategy_id,
            instrument=series.instrument,
            period=series.period,
            start_date=start_date,
            end_date=end_date,
            strategy_params=cs.parameters,
        )
        result = await run_backtest(request)
        return {
            "chart_strategy_id": str(cs_id),
            "chart_id": str(cs.chart_id),
            "strategy_id": cs.strategy_id,
            "result": result.model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backtest failed: {e}")
