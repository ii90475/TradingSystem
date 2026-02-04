"""Tests for monitoring service."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tradingsystem.services.monitoring_service import (
    ComponentHealth,
    ComponentStatus,
    MonitoringService,
)


# --- ComponentStatus Tests ---


class TestComponentStatus:
    """Tests for ComponentStatus enum."""

    def test_healthy_value(self):
        """Should have healthy status."""
        assert ComponentStatus.HEALTHY.value == "healthy"

    def test_unhealthy_value(self):
        """Should have unhealthy status."""
        assert ComponentStatus.UNHEALTHY.value == "unhealthy"

    def test_unknown_value(self):
        """Should have unknown status."""
        assert ComponentStatus.UNKNOWN.value == "unknown"


# --- ComponentHealth Tests ---


class TestComponentHealth:
    """Tests for ComponentHealth dataclass."""

    def test_default_values(self):
        """Should have sensible defaults."""
        health = ComponentHealth(name="Test")

        assert health.name == "Test"
        assert health.status == ComponentStatus.UNKNOWN
        assert health.last_check is None
        assert health.last_healthy is None
        assert health.error is None
        assert health.details == {}

    def test_custom_values(self):
        """Should accept custom values."""
        now = datetime.now(timezone.utc)
        health = ComponentHealth(
            name="Database",
            status=ComponentStatus.HEALTHY,
            last_check=now,
            last_healthy=now,
            error=None,
            details={"pool_size": 5},
        )

        assert health.name == "Database"
        assert health.status == ComponentStatus.HEALTHY
        assert health.details["pool_size"] == 5


# --- MonitoringService Init Tests ---


class TestMonitoringServiceInit:
    """Tests for MonitoringService initialization."""

    def test_initializes_components(self):
        """Should initialize all component trackers."""
        service = MonitoringService()

        assert "docker" in service._components
        assert "database" in service._components
        assert "rateservice" in service._components
        assert "oanda" in service._components
        assert "app" in service._components

    def test_starts_not_running(self):
        """Should start in non-running state."""
        service = MonitoringService()

        assert service.running is False
        assert service._scheduler is None

    def test_empty_alerted_failures(self):
        """Should start with no alerted failures."""
        service = MonitoringService()

        assert len(service._alerted_failures) == 0


# --- MonitoringService Start/Stop Tests ---


class TestMonitoringServiceStartStop:
    """Tests for start/stop methods."""

    @pytest.mark.asyncio
    async def test_start_when_disabled(self):
        """Should not start when monitoring disabled."""
        service = MonitoringService()

        with patch("tradingsystem.services.monitoring_service.settings") as mock_settings:
            mock_settings.monitoring_enabled = False

            await service.start()

            assert service.running is False

    @pytest.mark.asyncio
    async def test_start_when_enabled(self):
        """Should start when monitoring enabled."""
        service = MonitoringService()

        with patch("tradingsystem.services.monitoring_service.settings") as mock_settings:
            mock_settings.monitoring_enabled = True
            mock_settings.monitoring_interval_minutes = 5

            await service.start()

            assert service.running is True
            assert service._scheduler is not None

            # Cleanup
            await service.stop()

    @pytest.mark.asyncio
    async def test_start_idempotent(self):
        """Should not start twice."""
        service = MonitoringService()

        with patch("tradingsystem.services.monitoring_service.settings") as mock_settings:
            mock_settings.monitoring_enabled = True
            mock_settings.monitoring_interval_minutes = 5

            await service.start()
            scheduler1 = service._scheduler

            await service.start()  # Second call
            scheduler2 = service._scheduler

            assert scheduler1 is scheduler2

            # Cleanup
            await service.stop()

    @pytest.mark.asyncio
    async def test_stop(self):
        """Should stop monitoring."""
        service = MonitoringService()

        with patch("tradingsystem.services.monitoring_service.settings") as mock_settings:
            mock_settings.monitoring_enabled = True
            mock_settings.monitoring_interval_minutes = 5

            await service.start()
            await service.stop()

            assert service.running is False
            assert service._scheduler is None


# --- Health Check Tests ---


class TestHealthChecks:
    """Tests for individual health check methods."""

    @pytest.fixture
    def service(self):
        """Create monitoring service."""
        return MonitoringService()

    @pytest.mark.asyncio
    async def test_check_database_healthy(self, service):
        """Should record healthy database."""
        with patch("tradingsystem.services.monitoring_service.check_database_health") as mock_check:
            mock_check.return_value = {"healthy": True, "pool": {"size": 5}}

            await service._check_database()

            assert service._components["database"].status == ComponentStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_check_database_unhealthy(self, service):
        """Should record unhealthy database."""
        with patch("tradingsystem.services.monitoring_service.check_database_health") as mock_check, \
             patch("tradingsystem.services.monitoring_service.alert_service"):
            mock_check.return_value = {"healthy": False, "error": "Connection failed"}

            await service._check_database()

            assert service._components["database"].status == ComponentStatus.UNHEALTHY
            assert service._components["database"].error == "Connection failed"

    @pytest.mark.asyncio
    async def test_check_database_exception(self, service):
        """Should handle database check exception."""
        with patch("tradingsystem.services.monitoring_service.check_database_health") as mock_check, \
             patch("tradingsystem.services.monitoring_service.alert_service"):
            mock_check.side_effect = Exception("Unexpected error")

            await service._check_database()

            assert service._components["database"].status == ComponentStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_check_rateservice_healthy(self, service):
        """Should record healthy rateservice."""
        with patch("tradingsystem.services.monitoring_service.rateservice_client") as mock_client:
            mock_client.check_health = AsyncMock(return_value={"healthy": True, "status": "operational"})

            await service._check_rateservice()

            assert service._components["rateservice"].status == ComponentStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_check_rateservice_unhealthy(self, service):
        """Should record unhealthy rateservice."""
        with patch("tradingsystem.services.monitoring_service.rateservice_client") as mock_client, \
             patch("tradingsystem.services.monitoring_service.alert_service"):
            mock_client.check_health = AsyncMock(return_value={"healthy": False, "error": "Service down"})

            await service._check_rateservice()

            assert service._components["rateservice"].status == ComponentStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_check_oanda_when_disabled(self, service):
        """Should skip OANDA check when live trading disabled."""
        with patch("tradingsystem.services.monitoring_service.settings") as mock_settings:
            mock_settings.live_trading_enabled = False

            await service._check_oanda()

            assert service._components["oanda"].status == ComponentStatus.UNKNOWN
            assert "disabled" in service._components["oanda"].details.get("reason", "").lower()

    @pytest.mark.asyncio
    async def test_check_oanda_healthy(self, service):
        """Should record healthy OANDA."""
        with patch("tradingsystem.services.monitoring_service.settings") as mock_settings, \
             patch("tradingsystem.services.monitoring_service.oanda_trading_client") as mock_client:
            mock_settings.live_trading_enabled = True
            mock_client.check_connectivity = AsyncMock(return_value={
                "connected": True,
                "account_id": "101-001-123",
                "balance": "10000.00",
            })

            await service._check_oanda()

            assert service._components["oanda"].status == ComponentStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_check_oanda_unhealthy(self, service):
        """Should record unhealthy OANDA."""
        with patch("tradingsystem.services.monitoring_service.settings") as mock_settings, \
             patch("tradingsystem.services.monitoring_service.oanda_trading_client") as mock_client, \
             patch("tradingsystem.services.monitoring_service.alert_service"):
            mock_settings.live_trading_enabled = True
            mock_client.check_connectivity = AsyncMock(return_value={
                "connected": False,
                "error": "Authentication failed",
            })

            await service._check_oanda()

            assert service._components["oanda"].status == ComponentStatus.UNHEALTHY


# --- Record Healthy/Failure Tests ---


class TestRecordHealthyFailure:
    """Tests for _record_healthy and _record_failure methods."""

    @pytest.fixture
    def service(self):
        """Create monitoring service."""
        return MonitoringService()

    def test_record_healthy_sets_status(self, service):
        """Should set status to HEALTHY."""
        component = service._components["database"]

        service._record_healthy(component)

        assert component.status == ComponentStatus.HEALTHY
        assert component.last_healthy is not None
        assert component.error is None

    def test_record_healthy_alerts_on_recovery(self, service):
        """Should alert when recovering from failure."""
        component = service._components["database"]
        component.status = ComponentStatus.UNHEALTHY
        service._alerted_failures.add(component.name)

        with patch("tradingsystem.services.monitoring_service.alert_service") as mock_alert:
            service._record_healthy(component)

            mock_alert.create_alert.assert_called_once()
            assert component.name not in service._alerted_failures

    def test_record_failure_sets_status(self, service):
        """Should set status to UNHEALTHY."""
        component = service._components["database"]

        with patch("tradingsystem.services.monitoring_service.alert_service"):
            service._record_failure(component, "Connection error")

        assert component.status == ComponentStatus.UNHEALTHY
        assert component.error == "Connection error"

    def test_record_failure_alerts_once(self, service):
        """Should alert only on first failure."""
        component = service._components["database"]

        with patch("tradingsystem.services.monitoring_service.alert_service") as mock_alert:
            service._record_failure(component, "Error 1")
            service._record_failure(component, "Error 2")

            # Should only alert once
            assert mock_alert.create_alert.call_count == 1
            assert component.name in service._alerted_failures


# --- Get Status Tests ---


class TestGetStatus:
    """Tests for get_status method."""

    def test_returns_status_dict(self):
        """Should return complete status dict."""
        service = MonitoringService()

        with patch("tradingsystem.services.monitoring_service.settings") as mock_settings:
            mock_settings.monitoring_enabled = True
            mock_settings.monitoring_interval_minutes = 5

            status = service.get_status()

            assert "enabled" in status
            assert "running" in status
            assert "summary" in status
            assert "components" in status

    def test_counts_healthy_components(self):
        """Should count healthy/unhealthy components."""
        service = MonitoringService()
        service._components["database"].status = ComponentStatus.HEALTHY
        service._components["rateservice"].status = ComponentStatus.HEALTHY
        service._components["docker"].status = ComponentStatus.UNHEALTHY

        with patch("tradingsystem.services.monitoring_service.settings") as mock_settings:
            mock_settings.monitoring_enabled = True
            mock_settings.monitoring_interval_minutes = 5

            status = service.get_status()

            assert status["summary"]["healthy"] == 2
            assert status["summary"]["unhealthy"] == 3  # 3 unknown = unhealthy


# --- Run Check Now Tests ---


class TestRunCheckNow:
    """Tests for run_check_now method."""

    @pytest.mark.asyncio
    async def test_runs_health_checks(self):
        """Should run health checks and return status."""
        service = MonitoringService()

        with patch.object(service, "_run_health_checks", new_callable=AsyncMock) as mock_run, \
             patch("tradingsystem.services.monitoring_service.settings") as mock_settings:
            mock_settings.monitoring_enabled = True
            mock_settings.monitoring_interval_minutes = 5

            result = await service.run_check_now()

            mock_run.assert_called_once()
            assert "components" in result
