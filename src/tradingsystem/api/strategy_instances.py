"""API endpoints for strategy instance management."""

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from tradingsystem.services import strategy_instance_service
from tradingsystem.services.backtest_service import run_backtest
from tradingsystem.models.backtest import BacktestRequest
from tradingsystem.strategies.registry import StrategyRegistry

router = APIRouter(prefix="/strategy-instances", tags=["Strategy Instances"])


class CreateInstanceRequest(BaseModel):
    """Request body for creating a strategy instance."""

    name: str = Field(..., min_length=1, max_length=100, description="User-friendly name")
    strategy_id: str = Field(..., description="Base strategy ID (e.g., 'ma_crossover')")
    instrument: str = Field(..., description="Currency pair (e.g., 'GBP_USD')")
    period: str = Field(..., description="Timeframe (e.g., 'D', 'H1', 'M5')")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Strategy parameters")
    enabled: bool = Field(default=True, description="Enable for signal generation")


class UpdateInstanceRequest(BaseModel):
    """Request body for updating a strategy instance."""

    name: str | None = Field(None, min_length=1, max_length=100)
    parameters: dict[str, Any] | None = None
    enabled: bool | None = None


class InstanceResponse(BaseModel):
    """Response model for a strategy instance."""

    id: str
    name: str
    strategy_id: str
    instrument: str
    period: str
    parameters: dict[str, Any]
    enabled: bool
    created_at: str
    updated_at: str


@router.post("", response_model=InstanceResponse, status_code=201)
async def create_instance(request: CreateInstanceRequest) -> dict[str, Any]:
    """
    Create a new strategy instance.

    A strategy instance binds a generic strategy to a specific instrument,
    period, and parameter set, making it a trackable, reusable configuration.
    """
    try:
        instance = await strategy_instance_service.create_instance(
            name=request.name,
            strategy_id=request.strategy_id,
            instrument=request.instrument,
            period=request.period,
            parameters=request.parameters,
            enabled=request.enabled,
        )
        return instance.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        if "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail=f"Instance with name '{request.name}' already exists")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=list[InstanceResponse])
async def list_instances(
    strategy_id: str | None = None,
    instrument: str | None = None,
    enabled: bool | None = None,
) -> list[dict[str, Any]]:
    """
    List all strategy instances with optional filters.

    - **strategy_id**: Filter by base strategy (e.g., 'ma_crossover')
    - **instrument**: Filter by currency pair (e.g., 'GBP_USD')
    - **enabled**: Filter by enabled status (true/false)
    """
    instances = await strategy_instance_service.list_instances(
        strategy_id=strategy_id,
        instrument=instrument,
        enabled=enabled,
    )
    return [i.to_dict() for i in instances]


@router.get("/strategies")
async def list_available_strategies() -> list[dict[str, Any]]:
    """List all available base strategies that can be used to create instances."""
    return StrategyRegistry.list_all()


@router.get("/{instance_id}", response_model=InstanceResponse)
async def get_instance(instance_id: UUID) -> dict[str, Any]:
    """Get a strategy instance by ID."""
    instance = await strategy_instance_service.get_instance(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Strategy instance not found")
    return instance.to_dict()


@router.put("/{instance_id}", response_model=InstanceResponse)
async def update_instance(instance_id: UUID, request: UpdateInstanceRequest) -> dict[str, Any]:
    """
    Update a strategy instance.

    Note: strategy_id, instrument, and period cannot be changed after creation.
    Create a new instance if you need different values for these fields.
    """
    instance = await strategy_instance_service.update_instance(
        instance_id=instance_id,
        name=request.name,
        parameters=request.parameters,
        enabled=request.enabled,
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Strategy instance not found")
    return instance.to_dict()


@router.delete("/{instance_id}", status_code=204)
async def delete_instance(instance_id: UUID) -> None:
    """Delete a strategy instance."""
    deleted = await strategy_instance_service.delete_instance(instance_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Strategy instance not found")


@router.patch("/{instance_id}/toggle", response_model=InstanceResponse)
async def toggle_instance(instance_id: UUID) -> dict[str, Any]:
    """Toggle the enabled status of a strategy instance."""
    instance = await strategy_instance_service.toggle_enabled(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Strategy instance not found")
    return instance.to_dict()


@router.post("/{instance_id}/backtest")
async def run_instance_backtest(
    instance_id: UUID,
    days: int = 30,
) -> dict[str, Any]:
    """
    Run a backtest for this strategy instance.

    Uses the instance's saved strategy, instrument, period, and parameters.
    """
    instance = await strategy_instance_service.get_instance(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Strategy instance not found")

    try:
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)

        request = BacktestRequest(
            strategy_id=instance.strategy_id,
            instrument=instance.instrument,
            period=instance.period,
            start_date=start_date,
            end_date=end_date,
            strategy_params=instance.parameters,
        )
        result = await run_backtest(request)
        return {
            "instance_id": str(instance_id),
            "instance_name": instance.name,
            "result": result.model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backtest failed: {e}")
