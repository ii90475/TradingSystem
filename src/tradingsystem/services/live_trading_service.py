"""Live trading service for executing real trades via Oanda."""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from tradingsystem.core.config import settings
from tradingsystem.core.database import get_cursor
from tradingsystem.core.oanda_trading import oanda_trading_client, OandaOrderResponse
from tradingsystem.models.order import Order, OrderCreate, OrderSide, OrderStatus, OrderType, TradingMode
from tradingsystem.models.position import Position, PositionCreate, PositionSide, PositionStatus
from tradingsystem.services import order_service, position_service
from tradingsystem.services.risk_manager import risk_manager, RiskCheckResult

logger = logging.getLogger(__name__)


class LiveTradingError(Exception):
    """Error during live trading execution."""

    pass


async def execute_live_trade(
    instrument: str,
    side: OrderSide,
    quantity: Decimal,
    strategy_id: str | None = None,
    stop_loss: Decimal | None = None,
    take_profit: Decimal | None = None,
) -> tuple[Order, Position, OandaOrderResponse]:
    """
    Execute a live trade through Oanda.

    This function:
    1. Validates against risk limits
    2. Creates local order record
    3. Executes via Oanda API
    4. Updates local records with fill details
    5. Creates local position record

    Args:
        instrument: Currency pair (e.g., "EUR_USD")
        side: BUY or SELL
        quantity: Position size in units
        strategy_id: Optional strategy identifier
        stop_loss: Optional stop loss price
        take_profit: Optional take profit price

    Returns:
        Tuple of (Order, Position, OandaOrderResponse)

    Raises:
        LiveTradingError: If trade fails risk checks or execution
    """
    # Step 1: Risk check
    risk_result = await risk_manager.check_trade(instrument, side, quantity)
    if not risk_result.approved:
        raise LiveTradingError(
            f"Trade rejected by risk manager: {', '.join(risk_result.messages)}"
        )

    # Step 2: Create local order record (PENDING)
    local_order = await order_service.create_order(
        OrderCreate(
            instrument=instrument,
            side=side,
            order_type=OrderType.MARKET,
            quantity=quantity,
            strategy_id=strategy_id,
            mode=TradingMode.LIVE,
        )
    )

    try:
        # Step 3: Execute via Oanda
        # Convert side to units (positive for buy, negative for sell)
        units = quantity if side == OrderSide.BUY else -quantity

        oanda_response = await oanda_trading_client.create_market_order(
            instrument=instrument,
            units=units,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

        # Step 4: Update local order with fill
        filled_order = await order_service.fill_order(
            local_order.id,
            oanda_response.price,
            quantity,
        )

        # Update external_id with Oanda order ID
        await _update_order_external_id(filled_order.id, oanda_response.order_id)

        # Step 5: Create local position
        position_side = PositionSide.LONG if side == OrderSide.BUY else PositionSide.SHORT
        local_position = await position_service.open_position(
            PositionCreate(
                instrument=instrument,
                side=position_side,
                quantity=quantity,
                entry_price=oanda_response.price,
                strategy_id=strategy_id,
            )
        )

        # Update position with Oanda trade ID
        if oanda_response.trade_id:
            await _update_position_external_id(local_position.id, oanda_response.trade_id)

        logger.info(
            "live_trade_executed",
            extra={
                "event": "live_trade",
                "action": "execute",
                "order_id": str(filled_order.id),
                "position_id": str(local_position.id),
                "oanda_order_id": oanda_response.order_id,
                "oanda_trade_id": oanda_response.trade_id,
                "instrument": instrument,
                "side": side.value,
                "quantity": str(quantity),
                "fill_price": str(oanda_response.price),
            },
        )

        return filled_order, local_position, oanda_response

    except Exception as e:
        # Mark local order as failed
        await _mark_order_failed(local_order.id, str(e))
        logger.error(
            "live_trade_failed",
            extra={
                "order_id": str(local_order.id),
                "error": str(e),
            },
        )
        raise LiveTradingError(f"Oanda execution failed: {e}") from e


async def close_live_trade(
    position_id: UUID,
    oanda_trade_id: str | None = None,
) -> tuple[Order, Position, OandaOrderResponse]:
    """
    Close a live trade.

    Args:
        position_id: Local position UUID
        oanda_trade_id: Optional Oanda trade ID (will lookup if not provided)

    Returns:
        Tuple of (Order, Position, OandaOrderResponse)
    """
    position = await position_service.get_position(position_id)
    if not position:
        raise LiveTradingError(f"Position not found: {position_id}")

    if position.status != PositionStatus.OPEN:
        raise LiveTradingError(f"Position is not open: {position.status}")

    # Get Oanda trade ID if not provided
    if not oanda_trade_id:
        oanda_trade_id = await _get_position_external_id(position_id)
        if not oanda_trade_id:
            raise LiveTradingError(f"No Oanda trade ID for position {position_id}")

    # Create closing order
    close_side = OrderSide.SELL if position.side == PositionSide.LONG else OrderSide.BUY

    local_order = await order_service.create_order(
        OrderCreate(
            instrument=position.instrument,
            side=close_side,
            order_type=OrderType.MARKET,
            quantity=position.quantity,
            strategy_id=position.strategy_id,
            mode=TradingMode.LIVE,
        )
    )

    try:
        # Close via Oanda
        oanda_response = await oanda_trading_client.close_trade(oanda_trade_id)

        # Update local order
        filled_order = await order_service.fill_order(
            local_order.id,
            oanda_response.price,
            position.quantity,
        )

        # Close local position
        closed_position = await position_service.close_position(
            position_id,
            oanda_response.price,
        )

        # Record result for risk tracking
        if closed_position.pnl:
            risk_manager.record_trade_result(closed_position.pnl)

        logger.info(
            "live_trade_closed",
            extra={
                "event": "live_trade",
                "action": "close",
                "order_id": str(filled_order.id),
                "position_id": str(position_id),
                "oanda_trade_id": oanda_trade_id,
                "exit_price": str(oanda_response.price),
                "pnl": str(closed_position.pnl),
            },
        )

        return filled_order, closed_position, oanda_response

    except Exception as e:
        await _mark_order_failed(local_order.id, str(e))
        logger.error(f"Failed to close live trade: {e}")
        raise LiveTradingError(f"Failed to close trade: {e}") from e


async def emergency_close_all() -> list[dict]:
    """
    Emergency: Close all open Oanda trades.

    Returns:
        List of close results
    """
    if not settings.live_trading_enabled:
        raise LiveTradingError("Live trading is not enabled")

    results = []

    try:
        close_responses = await oanda_trading_client.close_all_trades()

        for response in close_responses:
            results.append({
                "trade_id": response.trade_id,
                "instrument": response.instrument,
                "price": str(response.price),
                "status": "closed",
            })

        logger.warning(f"Emergency closed {len(results)} trades")

    except Exception as e:
        logger.error(f"Emergency close failed: {e}")
        raise LiveTradingError(f"Emergency close failed: {e}") from e

    return results


async def get_live_account_status() -> dict:
    """
    Get combined live trading status.

    Returns:
        Dict with account and risk status
    """
    try:
        oanda_status = await oanda_trading_client.check_connectivity()
        account = None

        if oanda_status["connected"]:
            account = await oanda_trading_client.get_account_summary()

        risk_status = risk_manager.get_risk_status()

        return {
            "mode": "LIVE" if settings.live_trading_enabled else "PAPER",
            "oanda": {
                "connected": oanda_status["connected"],
                "error": oanda_status.get("error"),
            },
            "account": {
                "balance": str(account.balance) if account else None,
                "nav": str(account.nav) if account else None,
                "unrealized_pnl": str(account.unrealized_pnl) if account else None,
                "margin_used": str(account.margin_used) if account else None,
                "margin_available": str(account.margin_available) if account else None,
                "open_trades": account.open_trade_count if account else 0,
            }
            if account
            else None,
            "risk": risk_status,
        }

    except Exception as e:
        return {
            "mode": "PAPER",
            "error": str(e),
            "oanda": {"connected": False, "error": str(e)},
            "account": None,
            "risk": risk_manager.get_risk_status(),
        }


async def _update_order_external_id(order_id: UUID, external_id: str) -> None:
    """Update order with Oanda order ID."""
    async with get_cursor() as cur:
        await cur.execute(
            "UPDATE orders SET external_id = %s WHERE id = %s",
            (external_id, order_id),
        )
        await cur.connection.commit()


async def _update_position_external_id(position_id: UUID, external_id: str) -> None:
    """Update position with Oanda trade ID (stored in strategy_id for now)."""
    # Note: Could add external_id column to positions table
    async with get_cursor() as cur:
        await cur.execute(
            """
            UPDATE positions
            SET strategy_id = COALESCE(strategy_id || ':' || %s, %s)
            WHERE id = %s
            """,
            (external_id, external_id, position_id),
        )
        await cur.connection.commit()


async def _get_position_external_id(position_id: UUID) -> str | None:
    """Get Oanda trade ID from position."""
    async with get_cursor() as cur:
        await cur.execute(
            "SELECT strategy_id FROM positions WHERE id = %s",
            (position_id,),
        )
        row = await cur.fetchone()
        if row and row["strategy_id"]:
            # Extract Oanda trade ID (after colon if present)
            parts = row["strategy_id"].split(":")
            return parts[-1] if len(parts) > 1 else None
        return None


async def _mark_order_failed(order_id: UUID, error: str) -> None:
    """Mark order as rejected with error message."""
    async with get_cursor() as cur:
        await cur.execute(
            "UPDATE orders SET status = %s WHERE id = %s",
            (OrderStatus.REJECTED.value, order_id),
        )
        await cur.connection.commit()
