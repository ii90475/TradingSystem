"""Live trading API endpoints."""

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from tradingsystem.core.config import settings
from tradingsystem.core.oanda_trading import oanda_trading_client
from tradingsystem.models.order import Order, OrderSide
from tradingsystem.models.position import Position
from tradingsystem.services import live_trading_service, reconciliation_service
from tradingsystem.services.live_trading_service import LiveTradingError
from tradingsystem.services.risk_manager import risk_manager

router = APIRouter(prefix="/live", tags=["live-trading"])


class LiveTradeRequest(BaseModel):
    """Request model for executing a live trade."""

    instrument: str
    side: OrderSide
    quantity: Decimal
    strategy_id: str | None = None
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None


class LiveTradeResponse(BaseModel):
    """Response model for executed live trade."""

    order: Order
    position: Position
    oanda_order_id: str
    oanda_trade_id: str | None
    message: str


class RiskCheckRequest(BaseModel):
    """Request model for risk check."""

    instrument: str
    side: OrderSide
    quantity: Decimal


class TradingModeRequest(BaseModel):
    """Request model for switching trading mode."""

    mode: str  # "PAPER" or "LIVE"
    confirm_live: bool = False  # Must be True to switch to LIVE


@router.get("/mode")
async def get_trading_mode() -> dict:
    """Get current trading mode (PAPER or LIVE)."""
    return {
        "mode": oanda_trading_client.trading_mode,
        "live_trading_enabled": settings.live_trading_enabled,
    }


@router.post("/mode")
async def set_trading_mode(request: TradingModeRequest) -> dict:
    """
    Switch trading mode between PAPER and LIVE.

    Switching to LIVE requires confirm_live=true and LIVE_TRADING_ENABLED=true.
    """
    mode = request.mode.upper()
    if mode not in ("PAPER", "LIVE"):
        raise HTTPException(status_code=400, detail="Mode must be PAPER or LIVE")

    if mode == "LIVE":
        if not settings.live_trading_enabled:
            raise HTTPException(
                status_code=403,
                detail="Live trading is disabled. Set LIVE_TRADING_ENABLED=true to enable.",
            )
        if not request.confirm_live:
            raise HTTPException(
                status_code=400,
                detail="Must set confirm_live=true to switch to LIVE mode.",
            )

    try:
        oanda_trading_client.set_trading_mode(mode)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "mode": oanda_trading_client.trading_mode,
        "message": f"Trading mode switched to {mode}",
    }


@router.get("/status")
async def get_live_status() -> dict:
    """
    Get live trading system status.

    Returns account info, risk status, and connectivity.
    """
    return await live_trading_service.get_live_account_status()


@router.get("/account")
async def get_account_summary() -> dict:
    """Get Oanda account summary."""
    try:
        account = await oanda_trading_client.get_account_summary()
        return {
            "account_id": account.id,
            "balance": str(account.balance),
            "nav": str(account.nav),
            "unrealized_pnl": str(account.unrealized_pnl),
            "margin_used": str(account.margin_used),
            "margin_available": str(account.margin_available),
            "open_trade_count": account.open_trade_count,
            "open_position_count": account.open_position_count,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/trades")
async def get_open_trades() -> list[dict]:
    """Get all open Oanda trades."""
    try:
        trades = await oanda_trading_client.get_open_trades()
        return [
            {
                "id": t.id,
                "instrument": t.instrument,
                "units": str(t.units),
                "price": str(t.price),
                "unrealized_pnl": str(t.unrealized_pnl),
                "state": t.state,
                "open_time": t.open_time.isoformat(),
            }
            for t in trades
        ]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/trade", response_model=LiveTradeResponse)
async def execute_live_trade(request: LiveTradeRequest) -> LiveTradeResponse:
    """
    Execute a trade through Oanda.

    Uses the current trading mode (PAPER or LIVE) to select the correct OANDA environment.
    LIVE mode requires LIVE_TRADING_ENABLED=true in environment.
    Trade must pass all risk checks before execution.
    """
    if oanda_trading_client.trading_mode == "LIVE" and not settings.live_trading_enabled:
        raise HTTPException(
            status_code=403,
            detail="Live trading is disabled. Set LIVE_TRADING_ENABLED=true to enable.",
        )

    try:
        order, position, oanda_response = await live_trading_service.execute_live_trade(
            instrument=request.instrument,
            side=request.side,
            quantity=request.quantity,
            strategy_id=request.strategy_id,
            stop_loss=request.stop_loss,
            take_profit=request.take_profit,
        )

        return LiveTradeResponse(
            order=order,
            position=position,
            oanda_order_id=oanda_response.order_id,
            oanda_trade_id=oanda_response.trade_id,
            message=f"Live trade executed: {request.side.value} {request.quantity} {request.instrument} at {oanda_response.price}",
        )

    except LiveTradingError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Trade execution failed: {e}")


@router.post("/trade/{position_id}/close")
async def close_live_trade(position_id: UUID) -> dict:
    """Close a trade by position ID."""
    if oanda_trading_client.trading_mode == "LIVE" and not settings.live_trading_enabled:
        raise HTTPException(
            status_code=403,
            detail="Live trading is disabled.",
        )

    try:
        order, position, oanda_response = await live_trading_service.close_live_trade(
            position_id=position_id,
        )

        return {
            "order_id": str(order.id),
            "position_id": str(position.id),
            "exit_price": str(oanda_response.price),
            "pnl": str(position.pnl),
            "message": f"Trade closed at {oanda_response.price}",
        }

    except LiveTradingError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Close failed: {e}")


@router.post("/emergency-close")
async def emergency_close_all() -> dict:
    """
    Emergency: Close all open Oanda trades.

    Use with caution - this will close ALL positions immediately.
    """
    if oanda_trading_client.trading_mode == "LIVE" and not settings.live_trading_enabled:
        raise HTTPException(
            status_code=403,
            detail="Live trading is disabled.",
        )

    try:
        results = await live_trading_service.emergency_close_all()
        return {
            "closed_count": len(results),
            "trades": results,
            "message": f"Emergency closed {len(results)} trades",
        }
    except LiveTradingError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/risk/check")
async def check_trade_risk(request: RiskCheckRequest) -> dict:
    """
    Check if a trade passes risk limits without executing.

    Returns approval status and any violations.
    """
    result = await risk_manager.check_trade(
        instrument=request.instrument,
        side=request.side,
        quantity=request.quantity,
    )

    return {
        "approved": result.approved,
        "violations": [v.value for v in result.violations],
        "messages": result.messages,
    }


@router.get("/risk/status")
async def get_risk_status() -> dict:
    """Get current risk management status."""
    return risk_manager.get_risk_status()


@router.post("/risk/reset-circuit-breaker")
async def reset_circuit_breaker() -> dict:
    """Manually reset the consecutive losses circuit breaker."""
    risk_manager.reset_circuit_breaker()
    return {"message": "Circuit breaker reset", "status": risk_manager.get_risk_status()}


@router.get("/reconciliation")
async def reconcile_positions() -> dict:
    """
    Compare local positions with Oanda.

    Returns discrepancies if positions are out of sync.
    """
    try:
        result = await reconciliation_service.reconcile_positions()
        return {
            "timestamp": result.timestamp.isoformat(),
            "oanda_positions": result.oanda_positions,
            "local_positions": result.local_positions,
            "in_sync": result.in_sync,
            "discrepancies": [
                {
                    "instrument": d.instrument,
                    "type": d.discrepancy_type,
                    "local_quantity": str(d.local_quantity) if d.local_quantity else None,
                    "oanda_quantity": str(d.oanda_quantity) if d.oanda_quantity else None,
                    "local_side": d.local_side,
                    "oanda_side": d.oanda_side,
                }
                for d in result.discrepancies
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/reconciliation/sync")
async def sync_positions() -> dict:
    """
    Sync local positions from Oanda (Oanda is source of truth).

    Will close local positions not found in Oanda.
    """
    try:
        return await reconciliation_service.sync_from_oanda()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/oanda/positions")
async def get_oanda_positions() -> dict:
    """Get detailed Oanda positions summary."""
    return await reconciliation_service.get_oanda_positions_summary()
