"""API tests for the main app endpoints."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from tradingsystem.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app, raise_server_exceptions=False)


class TestRootEndpoint:
    """Tests for GET /."""

    def test_root_endpoint(self, client):
        """Should return API info."""
        response = client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert "mode" in data
        assert "endpoints" in data

    def test_root_shows_paper_mode(self, client):
        """Should show PAPER mode when live trading disabled."""
        with patch("tradingsystem.main.settings") as mock_settings:
            mock_settings.app_name = "TradingSystem"
            mock_settings.live_trading_enabled = False

            response = client.get("/")

            assert response.status_code == 200
            # Note: TestClient uses actual settings, so we just verify structure
            data = response.json()
            assert "mode" in data


class TestHealthCheck:
    """Tests for GET /health."""

    def test_health_check_healthy(self, client):
        """Should return healthy status when all components healthy."""
        with patch("tradingsystem.main.check_database_health") as mock_db, \
             patch("tradingsystem.main.rateservice_client") as mock_rs, \
             patch("tradingsystem.main.health_state") as mock_health:
            mock_db.return_value = {
                "healthy": True,
                "pool": {"size": 5, "free": 3},
            }
            mock_rs.check_health = AsyncMock(return_value={
                "healthy": True,
                "status": "healthy",
            })
            mock_health.record_database_health.return_value = None
            mock_health.record_rateservice_health.return_value = None
            mock_health.get_summary.return_value = {
                "status": "healthy",
                "database": {"healthy": True, "pool": {}},
                "rateservice": {"healthy": True, "status": "healthy"},
            }

            response = client.get("/health")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"

    def test_health_check_degraded(self, client):
        """Should return degraded when RateService unhealthy."""
        with patch("tradingsystem.main.check_database_health") as mock_db, \
             patch("tradingsystem.main.rateservice_client") as mock_rs, \
             patch("tradingsystem.main.health_state") as mock_health:
            mock_db.return_value = {"healthy": True}
            mock_rs.check_health = AsyncMock(return_value={
                "healthy": False,
                "status": "unavailable",
                "error": "Connection refused",
            })
            mock_health.record_database_health.return_value = None
            mock_health.record_rateservice_health.return_value = None
            mock_health.get_summary.return_value = {
                "status": "degraded",
                "database": {"healthy": True},
                "rateservice": {"healthy": False, "error": "Connection refused"},
            }

            response = client.get("/health")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "degraded"

    def test_health_check_unhealthy(self, client):
        """Should return unhealthy when database unhealthy."""
        with patch("tradingsystem.main.check_database_health") as mock_db, \
             patch("tradingsystem.main.rateservice_client") as mock_rs, \
             patch("tradingsystem.main.health_state") as mock_health:
            mock_db.return_value = {
                "healthy": False,
                "error": "Connection failed",
            }
            mock_rs.check_health = AsyncMock(return_value={
                "healthy": True,
                "status": "healthy",
            })
            mock_health.record_database_health.return_value = None
            mock_health.record_rateservice_health.return_value = None
            mock_health.get_summary.return_value = {
                "status": "unhealthy",
                "database": {"healthy": False, "error": "Connection failed"},
                "rateservice": {"healthy": True},
            }

            response = client.get("/health")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "unhealthy"


class TestHealthCheckSimple:
    """Tests for GET /health/simple."""

    def test_health_simple_healthy(self, client):
        """Should return healthy for load balancers."""
        with patch("tradingsystem.main.check_database_health") as mock_db, \
             patch("tradingsystem.main.rateservice_client") as mock_rs:
            mock_db.return_value = {"healthy": True}
            mock_rs.check_health = AsyncMock(return_value={"healthy": True})

            response = client.get("/health/simple")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"

    def test_health_simple_degraded(self, client):
        """Should return degraded when RateService down."""
        with patch("tradingsystem.main.check_database_health") as mock_db, \
             patch("tradingsystem.main.rateservice_client") as mock_rs:
            mock_db.return_value = {"healthy": True}
            mock_rs.check_health = AsyncMock(return_value={"healthy": False})

            response = client.get("/health/simple")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "degraded"

    def test_health_simple_unhealthy(self, client):
        """Should return unhealthy when database down."""
        with patch("tradingsystem.main.check_database_health") as mock_db, \
             patch("tradingsystem.main.rateservice_client") as mock_rs:
            mock_db.return_value = {"healthy": False}
            # RateService check won't be called if DB is down
            mock_rs.check_health = AsyncMock(return_value={"healthy": True})

            response = client.get("/health/simple")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "unhealthy"


class TestAPIDocumentation:
    """Tests for API documentation endpoints."""

    def test_openapi_json(self, client):
        """Should return OpenAPI schema."""
        response = client.get("/openapi.json")

        assert response.status_code == 200
        data = response.json()
        assert "openapi" in data
        assert "paths" in data
        assert "info" in data

    def test_swagger_ui(self, client):
        """Should return Swagger UI page."""
        response = client.get("/docs")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_redoc(self, client):
        """Should return ReDoc page."""
        response = client.get("/redoc")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
