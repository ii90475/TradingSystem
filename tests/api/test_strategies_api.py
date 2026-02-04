"""API tests for the Strategies endpoints."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from tradingsystem.main import app
from tradingsystem.models.signal import Signal, SignalType


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def sample_signal():
    """Create a sample signal for testing."""
    return Signal(
        id=uuid4(),
        strategy_id="ma_crossover",
        instrument="EUR_USD",
        signal_type=SignalType.BUY,
        strength=Decimal("0.85"),
        time=datetime.now(timezone.utc),
        reason="SMA 20 crossed above SMA 50",
        metadata={"sma_20": 1.0860, "sma_50": 1.0840},
    )


class TestListStrategies:
    """Tests for GET /strategies."""

    def test_list_strategies(self, client):
        """Should return list of available strategies."""
        strategies = [
            {"id": "ma_crossover", "name": "MA Crossover", "description": "Moving average crossover"},
            {"id": "rsi_reversal", "name": "RSI Reversal", "description": "RSI overbought/oversold"},
        ]

        with patch("tradingsystem.api.strategies.strategy_service") as mock_service:
            mock_service.list_strategies.return_value = strategies

            response = client.get("/strategies")

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2

    def test_list_strategies_empty(self, client):
        """Should return empty list when no strategies registered."""
        with patch("tradingsystem.api.strategies.strategy_service") as mock_service:
            mock_service.list_strategies.return_value = []

            response = client.get("/strategies")

            assert response.status_code == 200
            assert response.json() == []


class TestGetRunningStrategies:
    """Tests for GET /strategies/running."""

    def test_get_running_strategies(self, client):
        """Should return running strategies."""
        running = [
            {
                "strategy_id": "ma_crossover",
                "instruments": ["EUR_USD"],
                "periods": ["M1"],
                "started_at": datetime.now(timezone.utc).isoformat(),
                "signals_generated": 5,
            }
        ]

        with patch("tradingsystem.api.strategies.strategy_service") as mock_service:
            mock_service.get_running_strategies.return_value = running

            response = client.get("/strategies/running")

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["strategy_id"] == "ma_crossover"

    def test_get_running_strategies_empty(self, client):
        """Should return empty list when none running."""
        with patch("tradingsystem.api.strategies.strategy_service") as mock_service:
            mock_service.get_running_strategies.return_value = []

            response = client.get("/strategies/running")

            assert response.status_code == 200
            assert response.json() == []


class TestGetStrategy:
    """Tests for GET /strategies/{strategy_id}."""

    def test_get_strategy_found(self, client):
        """Should return strategy details."""
        strategy_info = {
            "id": "ma_crossover",
            "name": "MA Crossover",
            "description": "Moving average crossover strategy",
            "version": "1.0.0",
            "instruments": ["EUR_USD", "GBP_USD"],
            "periods": ["M1", "M5"],
            "is_running": False,
        }

        with patch("tradingsystem.api.strategies.strategy_service") as mock_service:
            mock_service.get_strategy_info.return_value = strategy_info

            response = client.get("/strategies/ma_crossover")

            assert response.status_code == 200
            data = response.json()
            assert data["id"] == "ma_crossover"

    def test_get_strategy_not_found(self, client):
        """Should return 404 when strategy not found."""
        with patch("tradingsystem.api.strategies.strategy_service") as mock_service:
            mock_service.get_strategy_info.return_value = None

            response = client.get("/strategies/unknown_strategy")

            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()


class TestStartStrategy:
    """Tests for POST /strategies/{strategy_id}/start."""

    def test_start_strategy_success(self, client):
        """Should start strategy successfully."""
        start_result = {
            "status": "started",
            "strategy_id": "ma_crossover",
            "instruments": ["EUR_USD"],
            "periods": ["M1"],
            "params": {},
        }

        with patch("tradingsystem.api.strategies.strategy_service") as mock_service:
            mock_service.start_strategy.return_value = start_result

            response = client.post(
                "/strategies/ma_crossover/start",
                json={
                    "instruments": ["EUR_USD"],
                    "periods": ["M1"],
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "started"
            assert data["strategy_id"] == "ma_crossover"

    def test_start_strategy_with_params(self, client):
        """Should pass custom params to strategy."""
        start_result = {
            "status": "started",
            "strategy_id": "ma_crossover",
            "instruments": ["EUR_USD"],
            "periods": ["M1"],
            "params": {"short_period": 10, "long_period": 30},
        }

        with patch("tradingsystem.api.strategies.strategy_service") as mock_service:
            mock_service.start_strategy.return_value = start_result

            response = client.post(
                "/strategies/ma_crossover/start",
                json={
                    "instruments": ["EUR_USD"],
                    "periods": ["M1"],
                    "params": {"short_period": 10, "long_period": 30},
                },
            )

            assert response.status_code == 200
            mock_service.start_strategy.assert_called_once()

    def test_start_strategy_not_found(self, client):
        """Should return 400 when strategy not found."""
        with patch("tradingsystem.api.strategies.strategy_service") as mock_service:
            mock_service.start_strategy.side_effect = ValueError("Strategy not found")

            response = client.post(
                "/strategies/unknown/start",
                json={"instruments": ["EUR_USD"]},
            )

            assert response.status_code == 400

    def test_start_strategy_validation_error(self, client):
        """Should return 400 when strategy validation fails."""
        with patch("tradingsystem.api.strategies.strategy_service") as mock_service:
            mock_service.start_strategy.side_effect = ValueError(
                "Strategy validation failed: invalid instruments"
            )

            response = client.post(
                "/strategies/ma_crossover/start",
                json={"instruments": []},
            )

            assert response.status_code == 400


class TestStopStrategy:
    """Tests for POST /strategies/{strategy_id}/stop."""

    def test_stop_strategy_success(self, client):
        """Should stop running strategy."""
        stop_result = {
            "status": "stopped",
            "strategy_id": "ma_crossover",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "signals_generated": 10,
        }

        with patch("tradingsystem.api.strategies.strategy_service") as mock_service:
            mock_service.stop_strategy.return_value = stop_result

            response = client.post("/strategies/ma_crossover/stop")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "stopped"

    def test_stop_strategy_not_running(self, client):
        """Should return 400 when strategy not running."""
        with patch("tradingsystem.api.strategies.strategy_service") as mock_service:
            mock_service.stop_strategy.side_effect = ValueError("Strategy not running")

            response = client.post("/strategies/ma_crossover/stop")

            assert response.status_code == 400


class TestRunStrategyOnce:
    """Tests for POST /strategies/{strategy_id}/run-once."""

    def test_run_once_success(self, client, sample_signal):
        """Should run strategy and return signals."""
        with patch("tradingsystem.api.strategies.strategy_service") as mock_service:
            mock_service.run_strategy_once = AsyncMock(return_value=[sample_signal])

            response = client.post(
                "/strategies/ma_crossover/run-once",
                json={
                    "instrument": "EUR_USD",
                    "period": "M1",
                    "limit": 100,
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["signal_type"] == "BUY"

    def test_run_once_no_signals(self, client):
        """Should return empty list when no signals generated."""
        with patch("tradingsystem.api.strategies.strategy_service") as mock_service:
            mock_service.run_strategy_once = AsyncMock(return_value=[])

            response = client.post(
                "/strategies/ma_crossover/run-once",
                json={
                    "instrument": "EUR_USD",
                    "period": "M1",
                },
            )

            assert response.status_code == 200
            assert response.json() == []

    def test_run_once_strategy_not_found(self, client):
        """Should return 400 when strategy not found."""
        with patch("tradingsystem.api.strategies.strategy_service") as mock_service:
            mock_service.run_strategy_once = AsyncMock(
                side_effect=ValueError("Strategy not found")
            )

            response = client.post(
                "/strategies/unknown/run-once",
                json={"instrument": "EUR_USD"},
            )

            assert response.status_code == 400

    def test_run_once_execution_error(self, client):
        """Should return 500 on execution error."""
        with patch("tradingsystem.api.strategies.strategy_service") as mock_service:
            mock_service.run_strategy_once = AsyncMock(
                side_effect=Exception("Database connection failed")
            )

            response = client.post(
                "/strategies/ma_crossover/run-once",
                json={"instrument": "EUR_USD"},
            )

            assert response.status_code == 500


class TestGetStrategyStatus:
    """Tests for GET /strategies/{strategy_id}/status."""

    def test_get_status_running(self, client):
        """Should return running status."""
        with patch("tradingsystem.api.strategies.strategy_service") as mock_service:
            mock_service.is_strategy_running.return_value = True
            mock_service.get_strategy_info.return_value = {
                "name": "MA Crossover",
                "description": "Moving average crossover",
            }

            response = client.get("/strategies/ma_crossover/status")

            assert response.status_code == 200
            data = response.json()
            assert data["is_running"] is True
            assert data["strategy_id"] == "ma_crossover"

    def test_get_status_not_running(self, client):
        """Should return not running status."""
        with patch("tradingsystem.api.strategies.strategy_service") as mock_service:
            mock_service.is_strategy_running.return_value = False
            mock_service.get_strategy_info.return_value = {
                "name": "MA Crossover",
                "description": "Moving average crossover",
            }

            response = client.get("/strategies/ma_crossover/status")

            assert response.status_code == 200
            data = response.json()
            assert data["is_running"] is False

    def test_get_status_not_found(self, client):
        """Should return 404 when strategy not found."""
        with patch("tradingsystem.api.strategies.strategy_service") as mock_service:
            mock_service.is_strategy_running.return_value = False
            mock_service.get_strategy_info.return_value = None

            response = client.get("/strategies/unknown/status")

            assert response.status_code == 404
