"""Strategies API endpoints."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from tradingsystem.models.signal import Signal
from tradingsystem.services import strategy_service
from tradingsystem.services import strategy_generator_service

router = APIRouter(prefix="/strategies", tags=["strategies"])


class StrategyStartRequest(BaseModel):
    """Request model for starting a strategy."""

    instruments: list[str] | None = None
    periods: list[str] | None = None
    params: dict[str, Any] = {}


class StrategyStartResponse(BaseModel):
    """Response model for strategy start."""

    status: str
    strategy_id: str
    instruments: list[str]
    periods: list[str]
    params: dict[str, Any]


class StrategyStopResponse(BaseModel):
    """Response model for strategy stop."""

    status: str
    strategy_id: str
    started_at: str
    signals_generated: int


class RunOnceRequest(BaseModel):
    """Request model for running a strategy once."""

    instrument: str
    period: str = "M1"
    limit: int = 100
    start: datetime | None = None
    end: datetime | None = None


class GenerateStrategyRequest(BaseModel):
    """Request body for generating a strategy from plain English."""

    description: str = Field(
        ..., min_length=10, description="Plain English description of entry/exit conditions"
    )


class SaveStrategyRequest(BaseModel):
    """Request body for saving reviewed strategy code."""

    code: str = Field(..., min_length=50, description="Python strategy code to save")


class StrategyTestRequest(BaseModel):
    """Request body for testing strategy code on historical data."""

    code: str = Field(..., min_length=50, description="Python strategy code to test")
    instrument: str = Field(..., description="Currency pair (e.g., 'EUR_USD')")
    period: str = Field(default="H1", description="Timeframe (e.g., 'M5', 'H1', 'D')")
    limit: int = Field(default=200, ge=10, le=1000, description="Number of candles")
    start: datetime | None = Field(default=None, description="Start date for candle data")
    end: datetime | None = Field(default=None, description="End date for candle data")


@router.post("/generate")
async def generate_strategy(request: GenerateStrategyRequest) -> dict[str, Any]:
    """
    Generate strategy code from a plain English description.

    Calls Claude to produce a BaseStrategy subclass. Returns the code
    for review before saving.
    """
    try:
        result = await strategy_generator_service.generate_strategy(request.description)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Strategy generation failed: {e}")


@router.post("/save", status_code=201)
async def save_strategy(request: SaveStrategyRequest) -> dict[str, Any]:
    """
    Save reviewed strategy code to the strategies directory.

    Validates the code follows the BaseStrategy pattern, writes to disk,
    and registers in the StrategyRegistry.
    """
    try:
        result = strategy_generator_service.save_strategy(request.code)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/test")
async def run_strategy_test(request: StrategyTestRequest) -> dict[str, Any]:
    """
    Test strategy code on historical data without saving.

    Validates the code, runs it against candles, and returns
    generated signals and basic stats. No side effects.
    """
    try:
        result = await strategy_generator_service.test_strategy_code(
            code=request.code,
            instrument=request.instrument,
            period=request.period,
            limit=request.limit,
            start=request.start,
            end=request.end,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Strategy test failed: {e}")


@router.get("")
async def list_strategies() -> list[dict[str, Any]]:
    """List all available strategies."""
    return strategy_service.list_strategies()


@router.get("/running")
async def get_running_strategies() -> list[dict[str, Any]]:
    """Get list of currently running strategies."""
    return strategy_service.get_running_strategies()


@router.get("/{strategy_id}")
async def get_strategy(strategy_id: str) -> dict[str, Any]:
    """Get detailed information about a strategy."""
    info = strategy_service.get_strategy_info(strategy_id)
    if not info:
        raise HTTPException(status_code=404, detail=f"Strategy not found: {strategy_id}")
    return info


@router.post("/{strategy_id}/start", response_model=StrategyStartResponse)
async def start_strategy(
    strategy_id: str,
    request: StrategyStartRequest,
) -> StrategyStartResponse:
    """
    Start a strategy for execution.

    The strategy will be executed on each scheduler tick for the
    specified instruments and periods.
    """
    try:
        result = strategy_service.start_strategy(
            strategy_id=strategy_id,
            instruments=request.instruments,
            periods=request.periods,
            **request.params,
        )
        return StrategyStartResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{strategy_id}/stop", response_model=StrategyStopResponse)
async def stop_strategy(strategy_id: str) -> StrategyStopResponse:
    """Stop a running strategy."""
    try:
        result = strategy_service.stop_strategy(strategy_id)
        return StrategyStopResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{strategy_id}/run-once", response_model=list[Signal])
async def run_strategy_once(
    strategy_id: str,
    request: RunOnceRequest,
) -> list[Signal]:
    """
    Run a strategy once for testing.

    Executes the strategy against current market data and returns
    any generated signals. Signals are also saved to the database.
    """
    try:
        signals = await strategy_service.run_strategy_once(
            strategy_id=strategy_id,
            instrument=request.instrument,
            period=request.period,
            limit=request.limit,
            start=request.start,
            end=request.end,
        )
        return signals
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Strategy execution failed: {e}")


@router.get("/{strategy_id}/status")
async def get_strategy_status(strategy_id: str) -> dict[str, Any]:
    """Get the running status of a strategy."""
    is_running = strategy_service.is_strategy_running(strategy_id)
    info = strategy_service.get_strategy_info(strategy_id)

    if not info:
        raise HTTPException(status_code=404, detail=f"Strategy not found: {strategy_id}")

    return {
        "strategy_id": strategy_id,
        "is_running": is_running,
        "name": info.get("name"),
        "description": info.get("description"),
    }
