"""Positions API endpoints."""

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from tradingsystem.models.position import (
    Position,
    PositionClose,
    PositionSide,
    PositionStatus,
    PositionSummary,
)
from tradingsystem.services import paper_trading_service, position_service

router = APIRouter(prefix="/positions", tags=["positions"])


class CloseTradeResponse(BaseModel):
    """Response model for closing a trade."""

    position: Position
    order_id: UUID
    message: str


@router.get("", response_model=list[Position])
async def list_positions(
    status: PositionStatus | None = Query(None, description="Filter by position status"),
    instrument: str | None = Query(None, description="Filter by instrument"),
    strategy_id: str | None = Query(None, description="Filter by strategy"),
    limit: int = Query(100, ge=1, le=500, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Results offset"),
) -> list[Position]:
    """List positions with optional filtering."""
    return await position_service.list_positions(
        status=status,
        instrument=instrument,
        strategy_id=strategy_id,
        limit=limit,
        offset=offset,
    )


@router.get("/open", response_model=list[Position])
async def get_open_positions(
    instrument: str | None = Query(None, description="Filter by instrument"),
) -> list[Position]:
    """Get all open positions."""
    return await position_service.get_open_positions(instrument)


@router.get("/summary", response_model=PositionSummary)
async def get_position_summary() -> PositionSummary:
    """Get portfolio position summary with P&L calculations."""
    return await position_service.get_position_summary()


@router.get("/{position_id}", response_model=Position)
async def get_position(position_id: UUID) -> Position:
    """Get a position by ID."""
    position = await position_service.get_position(position_id)
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")
    return position


@router.post("/{position_id}/close", response_model=Position)
async def close_position(position_id: UUID, close_request: PositionClose) -> Position:
    """Close a position at specified price."""
    try:
        return await position_service.close_position(position_id, close_request.exit_price)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{position_id}/close-at-market", response_model=CloseTradeResponse)
async def close_position_at_market(position_id: UUID) -> CloseTradeResponse:
    """
    Close a position at current market price.

    Creates a closing order and closes the position with P&L calculation.
    """
    try:
        order, position = await paper_trading_service.close_trade(position_id)
        return CloseTradeResponse(
            position=position,
            order_id=order.id,
            message=f"Position closed at {position.exit_price}, P&L: {position.pnl}",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{position_id}/pnl")
async def get_position_pnl(position_id: UUID) -> dict:
    """Get current P&L for a position (unrealized if open)."""
    position = await position_service.get_position(position_id)
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")

    if position.status == PositionStatus.CLOSED:
        return {
            "position_id": str(position_id),
            "status": "CLOSED",
            "pnl": str(position.pnl),
            "pnl_percent": str(position.pnl_percent),
        }

    unrealized_pnl = await position_service.calculate_unrealized_pnl(position)
    pnl_percent = (unrealized_pnl / (position.entry_price * position.quantity)) * 100

    return {
        "position_id": str(position_id),
        "status": "OPEN",
        "unrealized_pnl": str(unrealized_pnl),
        "unrealized_pnl_percent": str(pnl_percent),
    }


@router.get("/account/summary")
async def get_account_summary() -> dict:
    """Get paper trading account summary."""
    return await paper_trading_service.get_account_summary()


@router.get("/market/price/{instrument}")
async def get_market_price(instrument: str) -> dict:
    """Get current market price for an instrument."""
    try:
        return await paper_trading_service.get_current_price(instrument)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
