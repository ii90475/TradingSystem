"""Tests for alert service."""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from tradingsystem.services.alert_service import (
    Alert,
    AlertLevel,
    AlertService,
    AlertThresholds,
    AlertType,
)


@pytest.fixture
def alert_service():
    """Create fresh alert service for each test."""
    return AlertService()


@pytest.fixture
def custom_thresholds():
    """Create custom thresholds for testing."""
    return AlertThresholds(
        drawdown_warning_pct=3.0,
        drawdown_critical_pct=7.0,
        daily_loss_warning_pct=0.5,
        daily_loss_critical_pct=1.0,
        consecutive_losses_warning=2,
        consecutive_losses_critical=4,
    )


class TestAlertServiceCreate:
    """Tests for AlertService.create_alert()."""

    def test_create_alert_basic(self, alert_service):
        """Should create alert with basic fields."""
        alert = alert_service.create_alert(
            AlertType.TRADE_EXECUTED,
            AlertLevel.INFO,
            "Trade executed successfully",
        )

        assert isinstance(alert, Alert)
        assert alert.type == AlertType.TRADE_EXECUTED
        assert alert.level == AlertLevel.INFO
        assert alert.message == "Trade executed successfully"
        assert alert.acknowledged is False

    def test_create_alert_with_data(self, alert_service):
        """Should include additional data."""
        alert = alert_service.create_alert(
            AlertType.TRADE_EXECUTED,
            AlertLevel.INFO,
            "Trade executed",
            {"instrument": "EUR_USD", "quantity": "1000"},
        )

        assert alert.data["instrument"] == "EUR_USD"
        assert alert.data["quantity"] == "1000"

    def test_create_alert_increments_counter(self, alert_service):
        """Should generate unique alert IDs."""
        alert1 = alert_service.create_alert(AlertType.TRADE_EXECUTED, AlertLevel.INFO, "Test 1")
        alert2 = alert_service.create_alert(AlertType.TRADE_EXECUTED, AlertLevel.INFO, "Test 2")

        assert alert1.id != alert2.id

    def test_create_alert_calls_handlers(self, alert_service):
        """Should dispatch to registered handlers."""
        handler = MagicMock()
        alert_service.register_handler(handler)

        alert = alert_service.create_alert(AlertType.TRADE_EXECUTED, AlertLevel.INFO, "Test")

        handler.assert_called_once_with(alert)

    def test_create_alert_handler_error_doesnt_propagate(self, alert_service):
        """Should catch handler errors."""
        handler = MagicMock(side_effect=Exception("Handler error"))
        alert_service.register_handler(handler)

        # Should not raise
        alert = alert_service.create_alert(AlertType.TRADE_EXECUTED, AlertLevel.INFO, "Test")

        assert alert is not None


class TestAlertServiceDrawdown:
    """Tests for AlertService.check_drawdown()."""

    def test_drawdown_no_alert_under_threshold(self, alert_service):
        """Should not alert when drawdown under warning threshold."""
        alert = alert_service.check_drawdown(
            current_balance=Decimal("9800"),
            peak_balance=Decimal("10000"),  # 2% drawdown
        )

        assert alert is None

    def test_drawdown_warning_alert(self, alert_service):
        """Should create warning at warning threshold."""
        alert = alert_service.check_drawdown(
            current_balance=Decimal("9400"),
            peak_balance=Decimal("10000"),  # 6% drawdown
        )

        assert alert is not None
        assert alert.level == AlertLevel.WARNING
        assert alert.type == AlertType.DRAWDOWN

    def test_drawdown_critical_alert(self, alert_service):
        """Should create critical at critical threshold."""
        alert = alert_service.check_drawdown(
            current_balance=Decimal("8900"),
            peak_balance=Decimal("10000"),  # 11% drawdown
        )

        assert alert is not None
        assert alert.level == AlertLevel.CRITICAL

    def test_drawdown_zero_peak(self, alert_service):
        """Should handle zero peak balance."""
        alert = alert_service.check_drawdown(
            current_balance=Decimal("100"),
            peak_balance=Decimal("0"),
        )

        assert alert is None


class TestAlertServiceDailyLoss:
    """Tests for AlertService.check_daily_loss()."""

    def test_daily_loss_no_alert_on_profit(self, alert_service):
        """Should not alert on profitable day."""
        alert = alert_service.check_daily_loss(
            daily_pnl=Decimal("100"),
            starting_balance=Decimal("10000"),
        )

        assert alert is None

    def test_daily_loss_warning_alert(self, alert_service):
        """Should create warning at warning threshold."""
        alert = alert_service.check_daily_loss(
            daily_pnl=Decimal("-150"),  # 1.5% loss
            starting_balance=Decimal("10000"),
        )

        assert alert is not None
        assert alert.level == AlertLevel.WARNING
        assert alert.type == AlertType.DAILY_LOSS

    def test_daily_loss_critical_alert(self, alert_service):
        """Should create critical at critical threshold."""
        alert = alert_service.check_daily_loss(
            daily_pnl=Decimal("-250"),  # 2.5% loss
            starting_balance=Decimal("10000"),
        )

        assert alert is not None
        assert alert.level == AlertLevel.CRITICAL


class TestAlertServiceConsecutiveLosses:
    """Tests for AlertService.check_consecutive_losses()."""

    def test_consecutive_losses_no_alert_under_threshold(self, alert_service):
        """Should not alert when under warning threshold."""
        alert = alert_service.check_consecutive_losses(2)

        assert alert is None

    def test_consecutive_losses_warning(self, alert_service):
        """Should create warning at warning threshold."""
        alert = alert_service.check_consecutive_losses(3)

        assert alert is not None
        assert alert.level == AlertLevel.WARNING
        assert alert.type == AlertType.CONSECUTIVE_LOSSES

    def test_consecutive_losses_critical(self, alert_service):
        """Should create critical at critical threshold."""
        alert = alert_service.check_consecutive_losses(5)

        assert alert is not None
        assert alert.level == AlertLevel.CRITICAL


class TestAlertServiceMargin:
    """Tests for AlertService.check_margin()."""

    def test_margin_no_alert_under_threshold(self, alert_service):
        """Should not alert when margin usage low."""
        alert = alert_service.check_margin(
            margin_used=Decimal("1000"),
            margin_available=Decimal("9000"),  # 10% used
        )

        assert alert is None

    def test_margin_warning_alert(self, alert_service):
        """Should create warning at threshold."""
        alert = alert_service.check_margin(
            margin_used=Decimal("6000"),
            margin_available=Decimal("4000"),  # 60% used
        )

        assert alert is not None
        assert alert.level == AlertLevel.WARNING
        assert alert.type == AlertType.MARGIN_WARNING


class TestAlertServiceTradeAlerts:
    """Tests for trade-related alerts."""

    def test_alert_trade_executed(self, alert_service):
        """Should create trade executed alert."""
        alert = alert_service.alert_trade_executed(
            instrument="EUR_USD",
            side="BUY",
            quantity=Decimal("1000"),
            price=Decimal("1.0850"),
        )

        assert alert.type == AlertType.TRADE_EXECUTED
        assert alert.level == AlertLevel.INFO

    def test_alert_trade_closed_profit(self, alert_service):
        """Should create INFO alert for profitable close."""
        alert = alert_service.alert_trade_closed(
            instrument="EUR_USD",
            pnl=Decimal("50.00"),
            pnl_pct=Decimal("0.46"),
        )

        assert alert.type == AlertType.TRADE_CLOSED
        assert alert.level == AlertLevel.INFO

    def test_alert_trade_closed_loss(self, alert_service):
        """Should create WARNING alert for losing close."""
        alert = alert_service.alert_trade_closed(
            instrument="EUR_USD",
            pnl=Decimal("-30.00"),
            pnl_pct=Decimal("-0.28"),
        )

        assert alert.type == AlertType.TRADE_CLOSED
        assert alert.level == AlertLevel.WARNING


class TestAlertServiceGetAlerts:
    """Tests for AlertService.get_alerts()."""

    def test_get_alerts_returns_recent_first(self, alert_service):
        """Should return alerts in reverse chronological order."""
        alert_service.create_alert(AlertType.TRADE_EXECUTED, AlertLevel.INFO, "First")
        alert_service.create_alert(AlertType.TRADE_EXECUTED, AlertLevel.INFO, "Second")

        alerts = alert_service.get_alerts()

        assert alerts[0].message == "Second"
        assert alerts[1].message == "First"

    def test_get_alerts_filter_by_level(self, alert_service):
        """Should filter by level."""
        alert_service.create_alert(AlertType.TRADE_EXECUTED, AlertLevel.INFO, "Info")
        alert_service.create_alert(AlertType.DRAWDOWN, AlertLevel.WARNING, "Warning")

        alerts = alert_service.get_alerts(level=AlertLevel.WARNING)

        assert len(alerts) == 1
        assert alerts[0].level == AlertLevel.WARNING

    def test_get_alerts_filter_by_type(self, alert_service):
        """Should filter by type."""
        alert_service.create_alert(AlertType.TRADE_EXECUTED, AlertLevel.INFO, "Trade")
        alert_service.create_alert(AlertType.DRAWDOWN, AlertLevel.WARNING, "Drawdown")

        alerts = alert_service.get_alerts(alert_type=AlertType.DRAWDOWN)

        assert len(alerts) == 1
        assert alerts[0].type == AlertType.DRAWDOWN

    def test_get_alerts_limit(self, alert_service):
        """Should respect limit parameter."""
        for i in range(10):
            alert_service.create_alert(AlertType.TRADE_EXECUTED, AlertLevel.INFO, f"Alert {i}")

        alerts = alert_service.get_alerts(limit=5)

        assert len(alerts) == 5


class TestAlertServiceAcknowledge:
    """Tests for alert acknowledgment."""

    def test_acknowledge_alert(self, alert_service):
        """Should acknowledge specific alert."""
        alert = alert_service.create_alert(AlertType.TRADE_EXECUTED, AlertLevel.INFO, "Test")

        result = alert_service.acknowledge_alert(alert.id)

        assert result is True
        assert alert.acknowledged is True

    def test_acknowledge_alert_not_found(self, alert_service):
        """Should return False for unknown alert."""
        result = alert_service.acknowledge_alert("unknown-id")

        assert result is False

    def test_acknowledge_all(self, alert_service):
        """Should acknowledge all alerts."""
        alert_service.create_alert(AlertType.TRADE_EXECUTED, AlertLevel.INFO, "Test 1")
        alert_service.create_alert(AlertType.TRADE_EXECUTED, AlertLevel.INFO, "Test 2")

        count = alert_service.acknowledge_all()

        assert count == 2

    def test_get_alerts_unacknowledged_only(self, alert_service):
        """Should filter to unacknowledged only."""
        alert1 = alert_service.create_alert(AlertType.TRADE_EXECUTED, AlertLevel.INFO, "Test 1")
        alert_service.create_alert(AlertType.TRADE_EXECUTED, AlertLevel.INFO, "Test 2")
        alert_service.acknowledge_alert(alert1.id)

        alerts = alert_service.get_alerts(unacknowledged_only=True)

        assert len(alerts) == 1
        assert alerts[0].acknowledged is False


class TestAlertServiceSummary:
    """Tests for AlertService.get_summary()."""

    def test_get_summary(self, alert_service):
        """Should return summary statistics."""
        alert_service.create_alert(AlertType.TRADE_EXECUTED, AlertLevel.INFO, "Info")
        alert_service.create_alert(AlertType.DRAWDOWN, AlertLevel.WARNING, "Warning")
        alert_service.create_alert(AlertType.DAILY_LOSS, AlertLevel.CRITICAL, "Critical")

        summary = alert_service.get_summary()

        assert summary["total_alerts"] == 3
        assert summary["unacknowledged"] == 3
        assert summary["by_level"]["INFO"] == 1
        assert summary["by_level"]["WARNING"] == 1
        assert summary["by_level"]["CRITICAL"] == 1
