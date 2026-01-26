"""Risk management service for trade validation and limits."""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum

from tradingsystem.core.config import settings
from tradingsystem.core.oanda_trading import oanda_trading_client
from tradingsystem.models.order import OrderSide
from tradingsystem.services import position_service

logger = logging.getLogger(__name__)


class RiskViolation(str, Enum):
    """Types of risk violations."""

    LIVE_TRADING_DISABLED = "LIVE_TRADING_DISABLED"
    MAX_POSITION_SIZE = "MAX_POSITION_SIZE"
    MAX_DAILY_LOSS = "MAX_DAILY_LOSS"
    MAX_OPEN_POSITIONS = "MAX_OPEN_POSITIONS"
    INSTRUMENT_LIMIT = "INSTRUMENT_LIMIT"
    CONSECUTIVE_LOSSES = "CONSECUTIVE_LOSSES"
    MARKET_CLOSED = "MARKET_CLOSED"


@dataclass
class RiskCheckResult:
    """Result of a risk check."""

    approved: bool
    violations: list[RiskViolation] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    adjusted_quantity: Decimal | None = None


@dataclass
class DailyStats:
    """Daily trading statistics for risk tracking."""

    date: date
    starting_balance: Decimal
    current_balance: Decimal
    realized_pnl: Decimal
    trades_count: int
    consecutive_losses: int


class RiskManager:
    """
    Risk management service.

    Validates trades against risk limits:
    - Max position size (% of account)
    - Max daily loss (% of account)
    - Max open positions
    - Consecutive loss circuit breaker
    """

    def __init__(self) -> None:
        self._daily_stats: DailyStats | None = None
        self._consecutive_losses = 0
        self._max_consecutive_losses = 5  # Circuit breaker threshold

    async def check_trade(
        self,
        instrument: str,
        side: OrderSide,
        quantity: Decimal,
    ) -> RiskCheckResult:
        """
        Validate a trade against all risk rules.

        Args:
            instrument: Currency pair
            side: BUY or SELL
            quantity: Proposed trade size

        Returns:
            RiskCheckResult with approval status and any violations
        """
        violations = []
        messages = []

        # Check 1: Live trading enabled
        if not settings.live_trading_enabled:
            violations.append(RiskViolation.LIVE_TRADING_DISABLED)
            messages.append("Live trading is disabled")
            return RiskCheckResult(
                approved=False,
                violations=violations,
                messages=messages,
            )

        # Get account state
        try:
            account = await oanda_trading_client.get_account_summary()
        except Exception as e:
            messages.append(f"Failed to get account: {e}")
            return RiskCheckResult(approved=False, violations=[], messages=messages)

        # Check 2: Max position size
        max_size = account.balance * Decimal(str(settings.max_position_size_pct / 100))
        # For forex, position value depends on pair - simplified check using units
        if quantity > max_size:
            violations.append(RiskViolation.MAX_POSITION_SIZE)
            messages.append(
                f"Position size {quantity} exceeds max {max_size} "
                f"({settings.max_position_size_pct}% of balance)"
            )

        # Check 3: Max open positions
        open_trades = await oanda_trading_client.get_open_trades()
        if len(open_trades) >= settings.max_open_positions:
            violations.append(RiskViolation.MAX_OPEN_POSITIONS)
            messages.append(
                f"Already at max open positions: {len(open_trades)}/{settings.max_open_positions}"
            )

        # Check 4: Max daily loss
        await self._update_daily_stats(account.balance)
        if self._daily_stats:
            daily_loss_limit = self._daily_stats.starting_balance * Decimal(
                str(settings.max_daily_loss_pct / 100)
            )
            current_loss = self._daily_stats.starting_balance - account.balance

            if current_loss >= daily_loss_limit:
                violations.append(RiskViolation.MAX_DAILY_LOSS)
                messages.append(
                    f"Daily loss limit reached: {current_loss} >= {daily_loss_limit} "
                    f"({settings.max_daily_loss_pct}%)"
                )

        # Check 5: Consecutive losses circuit breaker
        if self._consecutive_losses >= self._max_consecutive_losses:
            violations.append(RiskViolation.CONSECUTIVE_LOSSES)
            messages.append(
                f"Circuit breaker: {self._consecutive_losses} consecutive losses"
            )

        # Determine approval
        approved = len(violations) == 0

        if approved:
            logger.info(
                "risk_check_passed",
                extra={
                    "instrument": instrument,
                    "side": side.value,
                    "quantity": str(quantity),
                },
            )
        else:
            logger.warning(
                "risk_check_failed",
                extra={
                    "instrument": instrument,
                    "side": side.value,
                    "quantity": str(quantity),
                    "violations": [v.value for v in violations],
                },
            )

        return RiskCheckResult(
            approved=approved,
            violations=violations,
            messages=messages,
        )

    async def _update_daily_stats(self, current_balance: Decimal) -> None:
        """Update daily statistics, resetting at day boundary."""
        today = date.today()

        if self._daily_stats is None or self._daily_stats.date != today:
            # New day - reset stats
            self._daily_stats = DailyStats(
                date=today,
                starting_balance=current_balance,
                current_balance=current_balance,
                realized_pnl=Decimal("0"),
                trades_count=0,
                consecutive_losses=0,
            )
            self._consecutive_losses = 0
            logger.info(f"Daily stats reset. Starting balance: {current_balance}")
        else:
            self._daily_stats.current_balance = current_balance

    def record_trade_result(self, pnl: Decimal) -> None:
        """
        Record trade result for consecutive loss tracking.

        Args:
            pnl: Profit/loss from the trade
        """
        if pnl < 0:
            self._consecutive_losses += 1
            logger.info(f"Loss recorded. Consecutive losses: {self._consecutive_losses}")
        else:
            self._consecutive_losses = 0
            logger.info("Win recorded. Consecutive losses reset.")

        if self._daily_stats:
            self._daily_stats.realized_pnl += pnl
            self._daily_stats.trades_count += 1

    def reset_circuit_breaker(self) -> None:
        """Manually reset the consecutive losses circuit breaker."""
        self._consecutive_losses = 0
        logger.warning("Circuit breaker manually reset")

    def get_risk_status(self) -> dict:
        """
        Get current risk status.

        Returns:
            Dict with risk metrics
        """
        return {
            "live_trading_enabled": settings.live_trading_enabled,
            "max_position_size_pct": settings.max_position_size_pct,
            "max_daily_loss_pct": settings.max_daily_loss_pct,
            "max_open_positions": settings.max_open_positions,
            "consecutive_losses": self._consecutive_losses,
            "circuit_breaker_threshold": self._max_consecutive_losses,
            "circuit_breaker_active": self._consecutive_losses >= self._max_consecutive_losses,
            "daily_stats": {
                "date": str(self._daily_stats.date) if self._daily_stats else None,
                "starting_balance": str(self._daily_stats.starting_balance)
                if self._daily_stats
                else None,
                "realized_pnl": str(self._daily_stats.realized_pnl)
                if self._daily_stats
                else None,
                "trades_count": self._daily_stats.trades_count
                if self._daily_stats
                else 0,
            },
        }


# Singleton instance
risk_manager = RiskManager()
