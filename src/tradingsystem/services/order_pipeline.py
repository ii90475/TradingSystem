"""Signal-to-order pipeline.

Converts strategy-generated BUY/SELL signals into orders routed through
the OANDA API (paper or live based on current trading mode).

Applies risk controls before placing orders:
- Max position size (5% of account)
- Max daily loss (2% drawdown)
- Max open positions (5 concurrent)
- Consecutive loss circuit breaker

Each signal is processed independently — one rejection does not block others.
All orders are logged with trading mode, source strategy, signal strength, and reason.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from tradingsystem.core.config import settings
from tradingsystem.core.oanda_trading import oanda_trading_client
from tradingsystem.models.order import OrderSide, TradingMode
from tradingsystem.models.signal import Signal, SignalType
from tradingsystem.services.live_trading_service import (
    LiveTradingError,
    execute_live_trade,
)

logger = logging.getLogger(__name__)

# Minimum signal strength to trigger an order (0.0–1.0)
DEFAULT_MIN_SIGNAL_STRENGTH = Decimal("0.5")

# Default order size in units (overridable per chart strategy)
DEFAULT_ORDER_UNITS = Decimal("1000")


@dataclass
class OrderResult:
    """Result of processing a single signal through the pipeline."""

    signal: Signal
    action: str  # "order_placed", "rejected", "skipped", "error"
    reason: str
    order_id: str | None = None
    trading_mode: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


async def process_signals(
    signals: list[Signal],
    order_units: Decimal = DEFAULT_ORDER_UNITS,
    min_strength: Decimal = DEFAULT_MIN_SIGNAL_STRENGTH,
    auto_execute: bool = True,
) -> list[OrderResult]:
    """Process a batch of signals through the order pipeline.

    Args:
        signals: List of strategy-generated signals to process.
        order_units: Position size in currency units for each order.
        min_strength: Minimum signal strength to act on (0.0–1.0).
        auto_execute: If True, place orders. If False, dry-run (log only).

    Returns:
        List of OrderResult with outcome for each signal.
    """
    results: list[OrderResult] = []

    for signal in signals:
        result = await _process_single_signal(
            signal=signal,
            order_units=order_units,
            min_strength=min_strength,
            auto_execute=auto_execute,
        )
        results.append(result)

    # Summary log
    placed = sum(1 for r in results if r.action == "order_placed")
    rejected = sum(1 for r in results if r.action == "rejected")
    skipped = sum(1 for r in results if r.action == "skipped")
    errors = sum(1 for r in results if r.action == "error")

    if results:
        logger.info(
            f"Order pipeline: {len(results)} signals processed — "
            f"{placed} placed, {rejected} rejected, {skipped} skipped, {errors} errors"
        )

    return results


async def _process_single_signal(
    signal: Signal,
    order_units: Decimal,
    min_strength: Decimal,
    auto_execute: bool,
) -> OrderResult:
    """Process one signal through filtering, risk checks, and execution."""

    # Skip HOLD signals
    if signal.signal_type == SignalType.HOLD:
        return OrderResult(
            signal=signal,
            action="skipped",
            reason="HOLD signal — no action",
        )

    # Filter by strength
    if signal.strength < min_strength:
        return OrderResult(
            signal=signal,
            action="skipped",
            reason=f"Signal strength {signal.strength} below threshold {min_strength}",
        )

    # Dry-run mode
    if not auto_execute:
        return OrderResult(
            signal=signal,
            action="skipped",
            reason="Auto-execute disabled (dry-run mode)",
            trading_mode=oanda_trading_client.trading_mode,
            details={
                "would_place": True,
                "side": signal.signal_type.value,
                "units": str(order_units),
                "instrument": signal.instrument,
            },
        )

    # Map signal type to order side
    side = OrderSide.BUY if signal.signal_type == SignalType.BUY else OrderSide.SELL

    trading_mode = oanda_trading_client.trading_mode

    try:
        order, position, oanda_response = await execute_live_trade(
            instrument=signal.instrument,
            side=side,
            quantity=order_units,
            strategy_id=signal.strategy_id,
        )

        logger.info(
            f"Order placed: {side.value} {order_units} {signal.instrument} "
            f"[{trading_mode}] — strategy={signal.strategy_id}, "
            f"strength={signal.strength}, reason={signal.reason}"
        )

        return OrderResult(
            signal=signal,
            action="order_placed",
            reason=f"{side.value} {order_units} {signal.instrument}",
            order_id=str(order.id),
            trading_mode=trading_mode,
            details={
                "fill_price": str(oanda_response.price),
                "position_id": str(position.id),
                "oanda_order_id": oanda_response.order_id,
                "signal_strength": str(signal.strength),
                "signal_reason": signal.reason,
            },
        )

    except LiveTradingError as e:
        # Risk rejection or execution failure from live_trading_service
        error_msg = str(e)
        is_risk_rejection = "risk manager" in error_msg.lower()

        logger.warning(
            f"Order {'rejected' if is_risk_rejection else 'failed'}: "
            f"{side.value} {order_units} {signal.instrument} — {error_msg}"
        )

        return OrderResult(
            signal=signal,
            action="rejected" if is_risk_rejection else "error",
            reason=error_msg,
            trading_mode=trading_mode,
            details={
                "signal_strength": str(signal.strength),
                "signal_reason": signal.reason,
            },
        )

    except Exception as e:
        logger.error(
            f"Unexpected error processing signal for {signal.instrument}: {e}",
            exc_info=True,
        )

        return OrderResult(
            signal=signal,
            action="error",
            reason=str(e),
            trading_mode=trading_mode,
        )
