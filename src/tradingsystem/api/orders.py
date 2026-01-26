"""Orders API endpoints."""

from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from tradingsystem.models.order import Order, OrderCreate, OrderSide, OrderStatus, OrderType
from tradingsystem.services import order_service, paper_trading_service

router = APIRouter(prefix="/orders", tags=["orders"])


class TradeRequest(BaseModel):
    """Request model for executing a trade."""

    instrument: str
    side: OrderSide
    quantity: Decimal
    strategy_id: str | None = None


class TradeResponse(BaseModel):
    """Response model for executed trade."""

    order: Order
    position_id: UUID
    message: str


@router.get("", response_model=list[Order])
async def list_orders(
    status: OrderStatus | None = Query(None, description="Filter by order status"),
    instrument: str | None = Query(None, description="Filter by instrument"),
    strategy_id: str | None = Query(None, description="Filter by strategy"),
    limit: int = Query(100, ge=1, le=500, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Results offset"),
) -> list[Order]:
    """List orders with optional filtering."""
    return await order_service.list_orders(
        status=status,
        instrument=instrument,
        strategy_id=strategy_id,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=Order, status_code=201)
async def create_order(order: OrderCreate) -> Order:
    """
    Create a new order.

    For paper trading, market orders are filled immediately at current price.
    """
    try:
        return await order_service.create_order(order)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/pending", response_model=list[Order])
async def get_pending_orders(
    instrument: str | None = Query(None, description="Filter by instrument"),
) -> list[Order]:
    """Get all pending orders."""
    return await order_service.get_pending_orders(instrument)


@router.get("/{order_id}", response_model=Order)
async def get_order(order_id: UUID) -> Order:
    """Get an order by ID."""
    order = await order_service.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.delete("/{order_id}", response_model=Order)
async def cancel_order(order_id: UUID) -> Order:
    """Cancel a pending order."""
    try:
        return await order_service.cancel_order(order_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/trade", response_model=TradeResponse)
async def execute_trade(request: TradeRequest) -> TradeResponse:
    """
    Execute a paper trade.

    Creates a market order and opens a corresponding position.
    This is the primary endpoint for paper trading.
    """
    try:
        order, position = await paper_trading_service.execute_trade(
            instrument=request.instrument,
            side=request.side,
            quantity=request.quantity,
            strategy_id=request.strategy_id,
        )
        return TradeResponse(
            order=order,
            position_id=position.id,
            message=f"Trade executed: {request.side.value} {request.quantity} {request.instrument} at {order.filled_price}",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/count")
async def count_orders(
    status: OrderStatus | None = Query(None, description="Filter by status"),
) -> dict[str, int]:
    """Get count of orders."""
    count = await order_service.count_orders(status)
    return {"count": count}
