"""Alert service for monitoring and notifications."""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Callable

logger = logging.getLogger(__name__)


class AlertLevel(str, Enum):
    """Alert severity levels."""

    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AlertType(str, Enum):
    """Types of alerts."""

    DRAWDOWN = "DRAWDOWN"
    DAILY_LOSS = "DAILY_LOSS"
    CONSECUTIVE_LOSSES = "CONSECUTIVE_LOSSES"
    POSITION_SIZE = "POSITION_SIZE"
    MARGIN_WARNING = "MARGIN_WARNING"
    CONNECTION_ERROR = "CONNECTION_ERROR"
    STRATEGY_ERROR = "STRATEGY_ERROR"
    RECONCILIATION_ERROR = "RECONCILIATION_ERROR"
    TRADE_EXECUTED = "TRADE_EXECUTED"
    TRADE_CLOSED = "TRADE_CLOSED"
    COMPONENT_FAILURE = "COMPONENT_FAILURE"
    COMPONENT_RECOVERY = "COMPONENT_RECOVERY"
    LOG_RATE_EXCEEDED = "LOG_RATE_EXCEEDED"


@dataclass
class Alert:
    """An alert event."""

    id: str
    type: AlertType
    level: AlertLevel
    message: str
    timestamp: datetime
    data: dict = field(default_factory=dict)
    acknowledged: bool = False


@dataclass
class AlertThresholds:
    """Configurable alert thresholds."""

    drawdown_warning_pct: float = 5.0
    drawdown_critical_pct: float = 10.0
    daily_loss_warning_pct: float = 1.0
    daily_loss_critical_pct: float = 2.0
    margin_warning_pct: float = 50.0  # When margin used > this % of available
    consecutive_losses_warning: int = 3
    consecutive_losses_critical: int = 5


class AlertService:
    """
    Alert management service.

    Monitors trading activity and generates alerts based on configurable thresholds.
    Supports callback handlers for external notification integration.
    """

    def __init__(self, thresholds: AlertThresholds | None = None) -> None:
        self.thresholds = thresholds or AlertThresholds()
        self._alerts: list[Alert] = []
        self._handlers: list[Callable[[Alert], None]] = []
        self._alert_counter = 0

    def register_handler(self, handler: Callable[[Alert], None]) -> None:
        """
        Register an alert handler callback.

        Handlers are called when new alerts are created.
        Can be used for webhooks, email, Slack, etc.
        """
        self._handlers.append(handler)

    def create_alert(
        self,
        alert_type: AlertType,
        level: AlertLevel,
        message: str,
        data: dict | None = None,
    ) -> Alert:
        """
        Create and dispatch a new alert.

        Args:
            alert_type: Type of alert
            level: Severity level
            message: Human-readable message
            data: Optional additional data

        Returns:
            Created Alert object
        """
        self._alert_counter += 1
        alert = Alert(
            id=f"alert_{self._alert_counter}",
            type=alert_type,
            level=level,
            message=message,
            timestamp=datetime.now(timezone.utc),
            data=data or {},
        )

        self._alerts.append(alert)

        # Keep only last 1000 alerts
        if len(self._alerts) > 1000:
            self._alerts = self._alerts[-1000:]

        # Log alert
        log_method = {
            AlertLevel.INFO: logger.info,
            AlertLevel.WARNING: logger.warning,
            AlertLevel.CRITICAL: logger.critical,
        }.get(level, logger.info)

        log_method(
            f"ALERT [{level.value}] {alert_type.value}: {message}",
            extra={
                "alert_id": alert.id,
                "alert_type": alert_type.value,
                "alert_level": level.value,
                "alert_data": data,
            },
        )

        # Dispatch to handlers
        for handler in self._handlers:
            try:
                handler(alert)
            except Exception as e:
                logger.error(f"Alert handler error: {e}")

        return alert

    def check_drawdown(
        self,
        current_balance: Decimal,
        peak_balance: Decimal,
    ) -> Alert | None:
        """
        Check for drawdown alerts.

        Args:
            current_balance: Current account balance
            peak_balance: Highest balance achieved

        Returns:
            Alert if threshold exceeded, None otherwise
        """
        if peak_balance <= 0:
            return None

        drawdown_pct = float((peak_balance - current_balance) / peak_balance * 100)

        if drawdown_pct >= self.thresholds.drawdown_critical_pct:
            return self.create_alert(
                AlertType.DRAWDOWN,
                AlertLevel.CRITICAL,
                f"Critical drawdown: {drawdown_pct:.2f}% from peak",
                {
                    "current_balance": str(current_balance),
                    "peak_balance": str(peak_balance),
                    "drawdown_pct": drawdown_pct,
                },
            )
        elif drawdown_pct >= self.thresholds.drawdown_warning_pct:
            return self.create_alert(
                AlertType.DRAWDOWN,
                AlertLevel.WARNING,
                f"Drawdown warning: {drawdown_pct:.2f}% from peak",
                {
                    "current_balance": str(current_balance),
                    "peak_balance": str(peak_balance),
                    "drawdown_pct": drawdown_pct,
                },
            )

        return None

    def check_daily_loss(
        self,
        daily_pnl: Decimal,
        starting_balance: Decimal,
    ) -> Alert | None:
        """
        Check for daily loss alerts.

        Args:
            daily_pnl: P&L for today (negative = loss)
            starting_balance: Balance at start of day

        Returns:
            Alert if threshold exceeded, None otherwise
        """
        if starting_balance <= 0 or daily_pnl >= 0:
            return None

        loss_pct = float(abs(daily_pnl) / starting_balance * 100)

        if loss_pct >= self.thresholds.daily_loss_critical_pct:
            return self.create_alert(
                AlertType.DAILY_LOSS,
                AlertLevel.CRITICAL,
                f"Critical daily loss: {loss_pct:.2f}%",
                {
                    "daily_pnl": str(daily_pnl),
                    "starting_balance": str(starting_balance),
                    "loss_pct": loss_pct,
                },
            )
        elif loss_pct >= self.thresholds.daily_loss_warning_pct:
            return self.create_alert(
                AlertType.DAILY_LOSS,
                AlertLevel.WARNING,
                f"Daily loss warning: {loss_pct:.2f}%",
                {
                    "daily_pnl": str(daily_pnl),
                    "starting_balance": str(starting_balance),
                    "loss_pct": loss_pct,
                },
            )

        return None

    def check_consecutive_losses(self, count: int) -> Alert | None:
        """
        Check for consecutive loss alerts.

        Args:
            count: Number of consecutive losing trades

        Returns:
            Alert if threshold exceeded, None otherwise
        """
        if count >= self.thresholds.consecutive_losses_critical:
            return self.create_alert(
                AlertType.CONSECUTIVE_LOSSES,
                AlertLevel.CRITICAL,
                f"Critical: {count} consecutive losses - circuit breaker may trigger",
                {"consecutive_losses": count},
            )
        elif count >= self.thresholds.consecutive_losses_warning:
            return self.create_alert(
                AlertType.CONSECUTIVE_LOSSES,
                AlertLevel.WARNING,
                f"Warning: {count} consecutive losses",
                {"consecutive_losses": count},
            )

        return None

    def check_margin(
        self,
        margin_used: Decimal,
        margin_available: Decimal,
    ) -> Alert | None:
        """
        Check for margin utilization alerts.

        Args:
            margin_used: Current margin in use
            margin_available: Available margin

        Returns:
            Alert if threshold exceeded, None otherwise
        """
        total_margin = margin_used + margin_available
        if total_margin <= 0:
            return None

        used_pct = float(margin_used / total_margin * 100)

        if used_pct >= self.thresholds.margin_warning_pct:
            return self.create_alert(
                AlertType.MARGIN_WARNING,
                AlertLevel.WARNING,
                f"High margin utilization: {used_pct:.1f}%",
                {
                    "margin_used": str(margin_used),
                    "margin_available": str(margin_available),
                    "used_pct": used_pct,
                },
            )

        return None

    def alert_trade_executed(
        self,
        instrument: str,
        side: str,
        quantity: Decimal,
        price: Decimal,
    ) -> Alert:
        """Create alert for trade execution."""
        return self.create_alert(
            AlertType.TRADE_EXECUTED,
            AlertLevel.INFO,
            f"Trade executed: {side} {quantity} {instrument} @ {price}",
            {
                "instrument": instrument,
                "side": side,
                "quantity": str(quantity),
                "price": str(price),
            },
        )

    def alert_trade_closed(
        self,
        instrument: str,
        pnl: Decimal,
        pnl_pct: Decimal,
    ) -> Alert:
        """Create alert for trade closure."""
        level = AlertLevel.INFO if pnl >= 0 else AlertLevel.WARNING
        return self.create_alert(
            AlertType.TRADE_CLOSED,
            level,
            f"Trade closed: {instrument} P&L: {pnl} ({pnl_pct:.2f}%)",
            {
                "instrument": instrument,
                "pnl": str(pnl),
                "pnl_pct": str(pnl_pct),
            },
        )

    def alert_connection_error(self, service: str, error: str) -> Alert:
        """Create alert for connection errors."""
        return self.create_alert(
            AlertType.CONNECTION_ERROR,
            AlertLevel.CRITICAL,
            f"Connection error: {service} - {error}",
            {"service": service, "error": error},
        )

    def alert_reconciliation_error(self, discrepancies: int) -> Alert:
        """Create alert for position reconciliation issues."""
        return self.create_alert(
            AlertType.RECONCILIATION_ERROR,
            AlertLevel.WARNING,
            f"Position reconciliation found {discrepancies} discrepancies",
            {"discrepancy_count": discrepancies},
        )

    def get_alerts(
        self,
        level: AlertLevel | None = None,
        alert_type: AlertType | None = None,
        limit: int = 100,
        unacknowledged_only: bool = False,
    ) -> list[Alert]:
        """
        Get alerts with optional filtering.

        Args:
            level: Filter by level
            alert_type: Filter by type
            limit: Maximum alerts to return
            unacknowledged_only: Only return unacknowledged alerts

        Returns:
            List of Alert objects
        """
        alerts = self._alerts.copy()
        alerts.reverse()  # Most recent first

        if level:
            alerts = [a for a in alerts if a.level == level]

        if alert_type:
            alerts = [a for a in alerts if a.type == alert_type]

        if unacknowledged_only:
            alerts = [a for a in alerts if not a.acknowledged]

        return alerts[:limit]

    def acknowledge_alert(self, alert_id: str) -> bool:
        """
        Acknowledge an alert.

        Args:
            alert_id: Alert ID to acknowledge

        Returns:
            True if acknowledged, False if not found
        """
        for alert in self._alerts:
            if alert.id == alert_id:
                alert.acknowledged = True
                return True
        return False

    def acknowledge_all(self) -> int:
        """
        Acknowledge all alerts.

        Returns:
            Number of alerts acknowledged
        """
        count = 0
        for alert in self._alerts:
            if not alert.acknowledged:
                alert.acknowledged = True
                count += 1
        return count

    def get_summary(self) -> dict:
        """
        Get alert summary statistics.

        Returns:
            Dict with alert counts by level and type
        """
        unacked = [a for a in self._alerts if not a.acknowledged]

        return {
            "total_alerts": len(self._alerts),
            "unacknowledged": len(unacked),
            "by_level": {
                level.value: len([a for a in unacked if a.level == level])
                for level in AlertLevel
            },
            "by_type": {
                atype.value: len([a for a in unacked if a.type == atype])
                for atype in AlertType
            },
            "thresholds": {
                "drawdown_warning_pct": self.thresholds.drawdown_warning_pct,
                "drawdown_critical_pct": self.thresholds.drawdown_critical_pct,
                "daily_loss_warning_pct": self.thresholds.daily_loss_warning_pct,
                "daily_loss_critical_pct": self.thresholds.daily_loss_critical_pct,
                "margin_warning_pct": self.thresholds.margin_warning_pct,
                "consecutive_losses_warning": self.thresholds.consecutive_losses_warning,
                "consecutive_losses_critical": self.thresholds.consecutive_losses_critical,
            },
        }


# Singleton instance
alert_service = AlertService()
