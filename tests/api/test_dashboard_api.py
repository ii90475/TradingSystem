"""API tests for the Dashboard endpoints."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from tradingsystem.main import app
from tradingsystem.services.alert_service import AlertLevel, AlertType


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def sample_portfolio_snapshot():
    """Create sample portfolio snapshot."""
    mock_snapshot = MagicMock()
    mock_snapshot.timestamp = datetime.now(timezone.utc)
    mock_snapshot.account_balance = Decimal("10000.00")
    mock_snapshot.nav = Decimal("10050.00")
    mock_snapshot.unrealized_pnl = Decimal("50.00")
    mock_snapshot.realized_pnl = Decimal("500.00")
    mock_snapshot.open_positions = 2
    mock_snapshot.margin_used = Decimal("500.00")
    mock_snapshot.margin_available = Decimal("9500.00")
    mock_snapshot.daily_pnl = Decimal("75.00")
    mock_snapshot.weekly_pnl = Decimal("200.00")
    return mock_snapshot


@pytest.fixture
def sample_performance_metrics():
    """Create sample performance metrics."""
    mock_metrics = MagicMock()
    mock_metrics.period = "all_time"
    mock_metrics.start_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
    mock_metrics.end_date = datetime(2024, 1, 31, tzinfo=timezone.utc)
    mock_metrics.total_trades = 50
    mock_metrics.winning_trades = 30
    mock_metrics.losing_trades = 20
    mock_metrics.win_rate = 0.60
    mock_metrics.total_pnl = Decimal("1500.00")
    mock_metrics.gross_profit = Decimal("2500.00")
    mock_metrics.gross_loss = Decimal("1000.00")
    mock_metrics.profit_factor = 2.5
    mock_metrics.average_win = Decimal("83.33")
    mock_metrics.average_loss = Decimal("50.00")
    mock_metrics.largest_win = Decimal("200.00")
    mock_metrics.largest_loss = Decimal("100.00")
    mock_metrics.average_trade = Decimal("30.00")
    return mock_metrics


class TestGetPortfolioSnapshot:
    """Tests for GET /dashboard/portfolio."""

    def test_get_portfolio_snapshot(self, client, sample_portfolio_snapshot):
        """Should return portfolio snapshot."""
        with patch("tradingsystem.api.dashboard.performance_service") as mock_service:
            mock_service.get_portfolio_snapshot = AsyncMock(
                return_value=sample_portfolio_snapshot
            )

            response = client.get("/dashboard/portfolio")

            assert response.status_code == 200
            data = response.json()
            assert data["account_balance"] == "10000.00"
            assert data["nav"] == "10050.00"
            assert data["open_positions"] == 2


class TestGetPerformanceMetrics:
    """Tests for GET /dashboard/performance."""

    def test_get_performance_all_time(self, client, sample_performance_metrics):
        """Should return all-time performance."""
        with patch("tradingsystem.api.dashboard.performance_service") as mock_service:
            mock_service.get_performance_metrics = AsyncMock(
                return_value=sample_performance_metrics
            )

            response = client.get("/dashboard/performance")

            assert response.status_code == 200
            data = response.json()
            assert data["total_trades"] == 50
            assert data["win_rate"] == 60.0

    def test_get_performance_with_filters(self, client, sample_performance_metrics):
        """Should filter by period and strategy."""
        with patch("tradingsystem.api.dashboard.performance_service") as mock_service:
            mock_service.get_performance_metrics = AsyncMock(
                return_value=sample_performance_metrics
            )

            response = client.get(
                "/dashboard/performance",
                params={"period": "daily", "strategy_id": "ma_crossover"},
            )

            assert response.status_code == 200
            mock_service.get_performance_metrics.assert_called_once_with(
                "daily", "ma_crossover"
            )


class TestGetAllStrategyPerformance:
    """Tests for GET /dashboard/performance/strategies."""

    def test_get_all_strategy_performance(self, client):
        """Should return performance for all strategies."""
        mock_perf = MagicMock()
        mock_perf.strategy_id = "ma_crossover"
        mock_perf.total_trades = 20
        mock_perf.winning_trades = 12
        mock_perf.win_rate = 0.60
        mock_perf.total_pnl = Decimal("500.00")
        mock_perf.average_pnl = Decimal("25.00")
        mock_perf.max_drawdown = Decimal("100.00")

        with patch("tradingsystem.api.dashboard.performance_service") as mock_service:
            mock_service.get_all_strategy_performance = AsyncMock(return_value=[mock_perf])

            response = client.get("/dashboard/performance/strategies")

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["strategy_id"] == "ma_crossover"

    def test_get_all_strategy_performance_empty(self, client):
        """Should return empty list when no strategies have trades."""
        with patch("tradingsystem.api.dashboard.performance_service") as mock_service:
            mock_service.get_all_strategy_performance = AsyncMock(return_value=[])

            response = client.get("/dashboard/performance/strategies")

            assert response.status_code == 200
            assert response.json() == []


class TestGetTradeHistory:
    """Tests for GET /dashboard/trades."""

    def test_get_trade_history(self, client):
        """Should return trade history."""
        trades = [
            {
                "id": str(uuid4()),
                "instrument": "EUR_USD",
                "side": "LONG",
                "entry_price": "1.0850",
                "exit_price": "1.0900",
                "pnl": "50.00",
            }
        ]

        with patch("tradingsystem.api.dashboard.performance_service") as mock_service:
            mock_service.get_trade_history = AsyncMock(return_value=trades)

            response = client.get("/dashboard/trades")

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1

    def test_get_trade_history_with_filters(self, client):
        """Should filter by limit and strategy."""
        with patch("tradingsystem.api.dashboard.performance_service") as mock_service:
            mock_service.get_trade_history = AsyncMock(return_value=[])

            response = client.get(
                "/dashboard/trades",
                params={"limit": 25, "strategy_id": "rsi_reversal"},
            )

            assert response.status_code == 200
            mock_service.get_trade_history.assert_called_once_with(25, "rsi_reversal")


class TestGetEquityCurve:
    """Tests for GET /dashboard/equity-curve."""

    def test_get_equity_curve(self, client):
        """Should return equity curve data."""
        equity_data = [
            {"date": "2024-01-01", "cumulative_pnl": "100.00"},
            {"date": "2024-01-02", "cumulative_pnl": "150.00"},
        ]

        with patch("tradingsystem.api.dashboard.performance_service") as mock_service:
            mock_service.get_equity_curve = AsyncMock(return_value=equity_data)

            response = client.get("/dashboard/equity-curve")

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2

    def test_get_equity_curve_custom_days(self, client):
        """Should use custom days parameter."""
        with patch("tradingsystem.api.dashboard.performance_service") as mock_service:
            mock_service.get_equity_curve = AsyncMock(return_value=[])

            response = client.get("/dashboard/equity-curve", params={"days": 60})

            assert response.status_code == 200
            mock_service.get_equity_curve.assert_called_once_with(60)


class TestGetAlerts:
    """Tests for GET /dashboard/alerts."""

    def test_get_alerts(self, client):
        """Should return alerts."""
        mock_alert = MagicMock()
        mock_alert.id = "alert-123"
        mock_alert.type = AlertType.TRADE_EXECUTED
        mock_alert.level = AlertLevel.INFO
        mock_alert.message = "Trade executed successfully"
        mock_alert.timestamp = datetime.now(timezone.utc)
        mock_alert.data = {}
        mock_alert.acknowledged = False

        with patch("tradingsystem.api.dashboard.alert_service") as mock_service:
            mock_service.get_alerts.return_value = [mock_alert]

            response = client.get("/dashboard/alerts")

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["level"] == "INFO"

    def test_get_alerts_with_filters(self, client):
        """Should filter alerts by level and type."""
        with patch("tradingsystem.api.dashboard.alert_service") as mock_service:
            mock_service.get_alerts.return_value = []

            response = client.get(
                "/dashboard/alerts",
                params={
                    "level": "CRITICAL",
                    "unacknowledged_only": True,
                    "limit": 50,
                },
            )

            assert response.status_code == 200


class TestGetAlertSummary:
    """Tests for GET /dashboard/alerts/summary."""

    def test_get_alert_summary(self, client):
        """Should return alert summary."""
        summary = {
            "total": 10,
            "unacknowledged": 3,
            "by_level": {"INFO": 5, "WARNING": 3, "CRITICAL": 2},
        }

        with patch("tradingsystem.api.dashboard.alert_service") as mock_service:
            mock_service.get_summary.return_value = summary

            response = client.get("/dashboard/alerts/summary")

            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 10


class TestAcknowledgeAlert:
    """Tests for POST /dashboard/alerts/{alert_id}/acknowledge."""

    def test_acknowledge_alert_success(self, client):
        """Should acknowledge alert."""
        with patch("tradingsystem.api.dashboard.alert_service") as mock_service:
            mock_service.acknowledge_alert.return_value = True

            response = client.post("/dashboard/alerts/alert-123/acknowledge")

            assert response.status_code == 200
            data = response.json()
            assert data["acknowledged"] is True

    def test_acknowledge_alert_not_found(self, client):
        """Should return failure when alert not found."""
        with patch("tradingsystem.api.dashboard.alert_service") as mock_service:
            mock_service.acknowledge_alert.return_value = False

            response = client.post("/dashboard/alerts/unknown/acknowledge")

            assert response.status_code == 200
            data = response.json()
            assert data["acknowledged"] is False


class TestAcknowledgeAllAlerts:
    """Tests for POST /dashboard/alerts/acknowledge-all."""

    def test_acknowledge_all_alerts(self, client):
        """Should acknowledge all alerts."""
        with patch("tradingsystem.api.dashboard.alert_service") as mock_service:
            mock_service.acknowledge_all.return_value = 5

            response = client.post("/dashboard/alerts/acknowledge-all")

            assert response.status_code == 200
            data = response.json()
            assert data["acknowledged_count"] == 5


class TestGetMonitoringStatus:
    """Tests for GET /dashboard/monitoring."""

    def test_get_monitoring_status(self, client):
        """Should return monitoring status."""
        status = {
            "healthy": True,
            "last_check": datetime.now(timezone.utc).isoformat(),
            "checks": {"database": "OK", "rateservice": "OK"},
        }

        mock_log_stats = MagicMock()
        mock_log_stats.error_count = 0
        mock_log_stats.warning_count = 2
        mock_log_stats.window_seconds = 300
        mock_log_stats.error_threshold = 5
        mock_log_stats.warning_threshold = 10
        mock_log_stats.error_rate_exceeded = False
        mock_log_stats.warning_rate_exceeded = False

        with patch("tradingsystem.api.dashboard.monitoring_service") as mock_monitoring, \
             patch("tradingsystem.api.dashboard.get_log_monitor") as mock_log_monitor:
            mock_monitoring.get_status.return_value = status
            mock_log_monitor.return_value.get_stats.return_value = mock_log_stats

            response = client.get("/dashboard/monitoring")

            assert response.status_code == 200
            data = response.json()
            assert data["healthy"] is True

    def test_get_monitoring_status_no_log_monitor(self, client):
        """Should handle missing log monitor."""
        status = {"healthy": True}

        with patch("tradingsystem.api.dashboard.monitoring_service") as mock_monitoring, \
             patch("tradingsystem.api.dashboard.get_log_monitor") as mock_log_monitor:
            mock_monitoring.get_status.return_value = status
            mock_log_monitor.return_value = None

            response = client.get("/dashboard/monitoring")

            assert response.status_code == 200
            data = response.json()
            assert data["log_monitor"] is None


class TestRunMonitoringCheck:
    """Tests for POST /dashboard/monitoring/check."""

    def test_run_monitoring_check(self, client):
        """Should trigger monitoring check."""
        result = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "all_healthy": True,
            "checks": {"database": "OK", "rateservice": "OK"},
        }

        with patch("tradingsystem.api.dashboard.monitoring_service") as mock_service:
            mock_service.run_check_now = AsyncMock(return_value=result)

            response = client.post("/dashboard/monitoring/check")

            assert response.status_code == 200


class TestDashboardUI:
    """Tests for GET /dashboard/."""

    def test_dashboard_ui(self, client):
        """Should return HTML dashboard."""
        response = client.get("/dashboard/")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "TradingSystem Dashboard" in response.text
