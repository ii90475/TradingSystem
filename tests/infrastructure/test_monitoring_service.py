"""Tests for monitoring service."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tradingsystem.services.monitoring_service import (
    ComponentHealth,
    ComponentStatus,
    MonitoringService,
)


@pytest.fixture
def monitoring_service():
    """Create fresh monitoring service for each test."""
    return MonitoringService()


class TestMonitoringServiceInit:
    """Tests for MonitoringService initialization."""

    def test_init_creates_components(self, monitoring_service):
        """Should initialize all component health trackers."""
        assert "docker" in monitoring_service._components
        assert "database" in monitoring_service._components
        assert "rateservice" in monitoring_service._components
        assert "oanda" in monitoring_service._components
        assert "app" in monitoring_service._components

    def test_init_not_running(self, monitoring_service):
        """Should not be running on init."""
        assert monitoring_service.running is False


class TestMonitoringServiceStartStop:
    """Tests for MonitoringService start/stop."""

    @pytest.mark.asyncio
    async def test_start_creates_scheduler(self, monitoring_service):
        """Should create and start scheduler."""
        with patch("tradingsystem.services.monitoring_service.settings") as mock_settings:
            mock_settings.monitoring_enabled = True
            mock_settings.monitoring_interval_minutes = 1

            await monitoring_service.start()

            assert monitoring_service.running is True
            assert monitoring_service._scheduler is not None

            await monitoring_service.stop()

    @pytest.mark.asyncio
    async def test_start_disabled_by_config(self, monitoring_service):
        """Should not start when monitoring disabled."""
        with patch("tradingsystem.services.monitoring_service.settings") as mock_settings:
            mock_settings.monitoring_enabled = False

            await monitoring_service.start()

            assert monitoring_service.running is False

    @pytest.mark.asyncio
    async def test_stop_clears_scheduler(self, monitoring_service):
        """Should clear scheduler on stop."""
        with patch("tradingsystem.services.monitoring_service.settings") as mock_settings:
            mock_settings.monitoring_enabled = True
            mock_settings.monitoring_interval_minutes = 1

            await monitoring_service.start()
            await monitoring_service.stop()

            assert monitoring_service.running is False
            assert monitoring_service._scheduler is None


class TestMonitoringServiceDatabaseCheck:
    """Tests for database health check."""

    @pytest.mark.asyncio
    async def test_check_database_healthy(self, monitoring_service):
        """Should mark database as healthy on success."""
        with patch("tradingsystem.services.monitoring_service.check_database_health") as mock_check:
            mock_check.return_value = {"healthy": True, "pool": {"size": 5}}

            await monitoring_service._check_database()

            component = monitoring_service._components["database"]
            assert component.status == ComponentStatus.HEALTHY
            assert component.error is None

    @pytest.mark.asyncio
    async def test_check_database_unhealthy(self, monitoring_service):
        """Should mark database as unhealthy on failure."""
        with patch("tradingsystem.services.monitoring_service.check_database_health") as mock_check:
            mock_check.return_value = {"healthy": False, "error": "Connection refused"}

            await monitoring_service._check_database()

            component = monitoring_service._components["database"]
            assert component.status == ComponentStatus.UNHEALTHY
            assert "Connection refused" in component.error


class TestMonitoringServiceRateServiceCheck:
    """Tests for RateService health check."""

    @pytest.mark.asyncio
    async def test_check_rateservice_healthy(self, monitoring_service):
        """Should mark RateService as healthy on success."""
        with patch("tradingsystem.services.monitoring_service.rateservice_client") as mock_client:
            mock_client.check_health = AsyncMock(return_value={"healthy": True, "status": "healthy"})

            await monitoring_service._check_rateservice()

            component = monitoring_service._components["rateservice"]
            assert component.status == ComponentStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_check_rateservice_unhealthy(self, monitoring_service):
        """Should mark RateService as unhealthy on failure."""
        with patch("tradingsystem.services.monitoring_service.rateservice_client") as mock_client:
            mock_client.check_health = AsyncMock(return_value={"healthy": False, "error": "Timeout"})

            await monitoring_service._check_rateservice()

            component = monitoring_service._components["rateservice"]
            assert component.status == ComponentStatus.UNHEALTHY


class TestMonitoringServiceOandaCheck:
    """Tests for OANDA health check."""

    @pytest.mark.asyncio
    async def test_check_oanda_skips_when_disabled(self, monitoring_service):
        """Should skip OANDA check when live trading disabled."""
        with patch("tradingsystem.services.monitoring_service.settings") as mock_settings:
            mock_settings.live_trading_enabled = False

            await monitoring_service._check_oanda()

            component = monitoring_service._components["oanda"]
            assert component.status == ComponentStatus.UNKNOWN

    @pytest.mark.asyncio
    async def test_check_oanda_healthy(self, monitoring_service):
        """Should mark OANDA as healthy on success."""
        with patch("tradingsystem.services.monitoring_service.settings") as mock_settings, \
             patch("tradingsystem.services.monitoring_service.oanda_trading_client") as mock_client:
            mock_settings.live_trading_enabled = True
            mock_client.check_connectivity = AsyncMock(return_value={
                "connected": True,
                "account_id": "test-123",
                "balance": "10000.00",
            })

            await monitoring_service._check_oanda()

            component = monitoring_service._components["oanda"]
            assert component.status == ComponentStatus.HEALTHY


class TestMonitoringServiceAlerts:
    """Tests for monitoring alerts."""

    @pytest.mark.asyncio
    async def test_record_healthy_alerts_on_recovery(self, monitoring_service):
        """Should alert when component recovers."""
        with patch("tradingsystem.services.monitoring_service.alert_service") as mock_alerts:
            component = monitoring_service._components["database"]
            component.status = ComponentStatus.UNHEALTHY
            monitoring_service._alerted_failures.add("Database")

            monitoring_service._record_healthy(component)

            mock_alerts.create_alert.assert_called_once()
            assert "Database" not in monitoring_service._alerted_failures

    @pytest.mark.asyncio
    async def test_record_failure_alerts_first_time(self, monitoring_service):
        """Should alert on first failure only."""
        with patch("tradingsystem.services.monitoring_service.alert_service") as mock_alerts:
            component = monitoring_service._components["database"]

            monitoring_service._record_failure(component, "Connection error")

            mock_alerts.create_alert.assert_called_once()
            assert "Database" in monitoring_service._alerted_failures

    @pytest.mark.asyncio
    async def test_record_failure_no_duplicate_alerts(self, monitoring_service):
        """Should not alert on subsequent failures."""
        with patch("tradingsystem.services.monitoring_service.alert_service") as mock_alerts:
            component = monitoring_service._components["database"]
            monitoring_service._alerted_failures.add("Database")

            monitoring_service._record_failure(component, "Connection error")

            mock_alerts.create_alert.assert_not_called()


class TestMonitoringServiceGetStatus:
    """Tests for MonitoringService.get_status()."""

    def test_get_status_returns_all_components(self, monitoring_service):
        """Should return status for all components."""
        status = monitoring_service.get_status()

        assert "components" in status
        assert "docker" in status["components"]
        assert "database" in status["components"]
        assert "rateservice" in status["components"]
        assert "oanda" in status["components"]
        assert "app" in status["components"]

    def test_get_status_includes_summary(self, monitoring_service):
        """Should include healthy/unhealthy counts."""
        monitoring_service._components["database"].status = ComponentStatus.HEALTHY
        monitoring_service._components["rateservice"].status = ComponentStatus.UNHEALTHY

        status = monitoring_service.get_status()

        assert "summary" in status
        assert status["summary"]["healthy"] >= 1
        assert status["summary"]["unhealthy"] >= 1

    def test_get_status_includes_metadata(self, monitoring_service):
        """Should include monitoring metadata."""
        with patch("tradingsystem.services.monitoring_service.settings") as mock_settings:
            mock_settings.monitoring_enabled = True
            mock_settings.monitoring_interval_minutes = 5

            status = monitoring_service.get_status()

            assert status["enabled"] is True
            assert status["interval_minutes"] == 5


class TestMonitoringServiceRunCheckNow:
    """Tests for MonitoringService.run_check_now()."""

    @pytest.mark.asyncio
    async def test_run_check_now_triggers_all_checks(self, monitoring_service):
        """Should run all health checks and return status."""
        with patch.object(monitoring_service, "_run_health_checks") as mock_run:
            mock_run.return_value = None

            result = await monitoring_service.run_check_now()

            mock_run.assert_called_once()
            assert "components" in result


class TestComponentHealth:
    """Tests for ComponentHealth dataclass."""

    def test_component_health_defaults(self):
        """Should have sensible defaults."""
        component = ComponentHealth(name="Test")

        assert component.status == ComponentStatus.UNKNOWN
        assert component.last_check is None
        assert component.last_healthy is None
        assert component.error is None
        assert component.details == {}

    def test_component_status_enum(self):
        """Should enforce ComponentStatus enum values."""
        assert ComponentStatus.HEALTHY.value == "healthy"
        assert ComponentStatus.UNHEALTHY.value == "unhealthy"
        assert ComponentStatus.UNKNOWN.value == "unknown"
