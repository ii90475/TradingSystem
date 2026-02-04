"""Tests for health service."""

from datetime import datetime, timezone

import pytest

from tradingsystem.services.health import HealthState, HealthStatus


# --- HealthStatus Tests ---


class TestHealthStatus:
    """Tests for HealthStatus enum."""

    def test_healthy_value(self):
        """Should have healthy status."""
        assert HealthStatus.HEALTHY.value == "healthy"

    def test_degraded_value(self):
        """Should have degraded status."""
        assert HealthStatus.DEGRADED.value == "degraded"

    def test_unhealthy_value(self):
        """Should have unhealthy status."""
        assert HealthStatus.UNHEALTHY.value == "unhealthy"


# --- HealthState Tests ---


class TestHealthStateInit:
    """Tests for HealthState initialization."""

    def test_default_values(self):
        """Should have sensible defaults."""
        state = HealthState()

        assert state.database_healthy is True
        assert state.database_error is None
        assert state.rateservice_healthy is True
        assert state.rateservice_error is None
        assert state.rateservice_status == "unknown"
        assert state.scheduler_running is False
        assert state.last_health_check is None
        assert state.active_strategies == 0
        assert state.open_positions == 0


class TestRecordDatabaseHealth:
    """Tests for record_database_health method."""

    def test_records_healthy_state(self):
        """Should record healthy database state."""
        state = HealthState()

        state.record_database_health(healthy=True)

        assert state.database_healthy is True
        assert state.database_error is None

    def test_records_unhealthy_state(self):
        """Should record unhealthy database state."""
        state = HealthState()

        state.record_database_health(healthy=False, error="Connection failed")

        assert state.database_healthy is False
        assert state.database_error == "Connection failed"

    def test_clears_error_when_healthy(self):
        """Should clear error when database becomes healthy."""
        state = HealthState()
        state.database_error = "Previous error"

        state.record_database_health(healthy=True)

        assert state.database_error is None


class TestRecordRateserviceHealth:
    """Tests for record_rateservice_health method."""

    def test_records_healthy_state(self):
        """Should record healthy rateservice state."""
        state = HealthState()

        state.record_rateservice_health(healthy=True, status="operational")

        assert state.rateservice_healthy is True
        assert state.rateservice_status == "operational"
        assert state.rateservice_error is None

    def test_records_unhealthy_state(self):
        """Should record unhealthy rateservice state."""
        state = HealthState()

        state.record_rateservice_health(healthy=False, error="Service unavailable")

        assert state.rateservice_healthy is False
        assert state.rateservice_error == "Service unavailable"

    def test_records_degraded_status(self):
        """Should record degraded status."""
        state = HealthState()

        state.record_rateservice_health(healthy=True, status="degraded")

        assert state.rateservice_healthy is True
        assert state.rateservice_status == "degraded"


class TestGetStatus:
    """Tests for get_status method."""

    def test_returns_healthy_by_default(self):
        """Should return HEALTHY when all components healthy."""
        state = HealthState()

        status = state.get_status()

        assert status == HealthStatus.HEALTHY

    def test_returns_unhealthy_when_database_down(self):
        """Should return UNHEALTHY when database unhealthy."""
        state = HealthState()
        state.database_healthy = False

        status = state.get_status()

        assert status == HealthStatus.UNHEALTHY

    def test_returns_unhealthy_when_rateservice_down(self):
        """Should return UNHEALTHY when rateservice unhealthy."""
        state = HealthState()
        state.rateservice_healthy = False

        status = state.get_status()

        assert status == HealthStatus.UNHEALTHY

    def test_returns_degraded_when_rateservice_degraded(self):
        """Should return DEGRADED when rateservice is degraded."""
        state = HealthState()
        state.rateservice_status = "degraded"

        status = state.get_status()

        assert status == HealthStatus.DEGRADED

    def test_unhealthy_takes_precedence_over_degraded(self):
        """Should return UNHEALTHY even if also degraded."""
        state = HealthState()
        state.database_healthy = False
        state.rateservice_status = "degraded"

        status = state.get_status()

        assert status == HealthStatus.UNHEALTHY


class TestGetSummary:
    """Tests for get_summary method."""

    def test_returns_complete_summary(self):
        """Should return complete health summary."""
        state = HealthState()
        state.scheduler_running = True
        state.active_strategies = 3
        state.open_positions = 5

        summary = state.get_summary()

        assert "status" in summary
        assert "timestamp" in summary
        assert "database" in summary
        assert "rateservice" in summary
        assert summary["scheduler_running"] is True
        assert summary["active_strategies"] == 3
        assert summary["open_positions"] == 5

    def test_includes_database_info(self):
        """Should include database health info."""
        state = HealthState()
        state.database_healthy = False
        state.database_error = "Connection lost"

        summary = state.get_summary()

        assert summary["database"]["healthy"] is False
        assert summary["database"]["error"] == "Connection lost"

    def test_includes_rateservice_info(self):
        """Should include rateservice health info."""
        state = HealthState()
        state.rateservice_healthy = True
        state.rateservice_status = "operational"

        summary = state.get_summary()

        assert summary["rateservice"]["healthy"] is True
        assert summary["rateservice"]["status"] == "operational"

    def test_updates_last_health_check(self):
        """Should update last_health_check timestamp."""
        state = HealthState()
        assert state.last_health_check is None

        summary = state.get_summary()

        assert state.last_health_check is not None
        assert summary["timestamp"] == state.last_health_check.isoformat()

    def test_status_value_is_string(self):
        """Should return status as string value."""
        state = HealthState()

        summary = state.get_summary()

        assert summary["status"] == "healthy"
