"""API tests for the Backtest endpoints."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from tradingsystem.main import app
from tradingsystem.models.backtest import (
    BacktestConfig,
    BacktestResult,
    BacktestSummary,
    BacktestTrade,
    EquityPoint,
    PerformanceMetrics,
)


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def sample_backtest_result():
    """Create a sample backtest result for testing."""
    config = BacktestConfig(
        strategy_id="ma_crossover",
        instrument="EUR_USD",
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2024, 1, 31, tzinfo=timezone.utc),
        initial_capital=Decimal("10000.00"),
        period="M1",
    )

    metrics = PerformanceMetrics(
        total_return=Decimal("500.00"),
        total_return_pct=Decimal("5.0"),
        max_drawdown=Decimal("150.00"),
        max_drawdown_pct=Decimal("1.5"),
        win_rate=0.60,
        profit_factor=1.85,
        total_trades=20,
        winning_trades=12,
        losing_trades=8,
        avg_win=Decimal("60.00"),
        avg_loss=Decimal("27.50"),
        avg_trade=Decimal("25.00"),
        largest_win=Decimal("120.00"),
        largest_loss=Decimal("80.00"),
    )

    return BacktestResult(
        id=uuid4(),
        strategy_id="ma_crossover",
        instrument="EUR_USD",
        period="M1",
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2024, 1, 31, tzinfo=timezone.utc),
        initial_capital=Decimal("10000.00"),
        final_capital=Decimal("10500.00"),
        config=config,
        metrics=metrics,
        trades=[
            BacktestTrade(
                entry_time=datetime(2024, 1, 2, tzinfo=timezone.utc),
                exit_time=datetime(2024, 1, 2, 1, 0, tzinfo=timezone.utc),
                side="LONG",
                entry_price=Decimal("1.0850"),
                exit_price=Decimal("1.0900"),
                quantity=Decimal("1000"),
                pnl=Decimal("50.00"),
                pnl_pct=Decimal("0.46"),
            )
        ],
        equity_curve=[
            EquityPoint(
                time=datetime(2024, 1, 1, tzinfo=timezone.utc),
                equity=Decimal("10000.00"),
                drawdown=Decimal("0"),
            ),
            EquityPoint(
                time=datetime(2024, 1, 2, tzinfo=timezone.utc),
                equity=Decimal("10050.00"),
                drawdown=Decimal("0"),
            ),
        ],
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_backtest_summary():
    """Create a sample backtest summary for testing."""
    return BacktestSummary(
        id=uuid4(),
        strategy_id="ma_crossover",
        instrument="EUR_USD",
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2024, 1, 31, tzinfo=timezone.utc),
        total_return_pct=Decimal("5.0"),
        sharpe_ratio=1.25,
        max_drawdown_pct=Decimal("1.5"),
        total_trades=20,
        win_rate=0.60,
        created_at=datetime.now(timezone.utc),
    )


class TestRunBacktest:
    """Tests for POST /backtest."""

    def test_run_backtest_success(self, client, sample_backtest_result):
        """Should run backtest and return results."""
        with patch("tradingsystem.api.backtest.backtest_service") as mock_service:
            mock_service.run_backtest = AsyncMock(return_value=sample_backtest_result)

            response = client.post(
                "/backtest",
                json={
                    "strategy_id": "ma_crossover",
                    "instrument": "EUR_USD",
                    "period": "M1",
                    "start_date": "2024-01-01T00:00:00Z",
                    "end_date": "2024-01-31T00:00:00Z",
                    "initial_capital": "10000.00",
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["strategy_id"] == "ma_crossover"
            assert "metrics" in data
            assert "trades" in data

    def test_run_backtest_invalid_strategy(self, client):
        """Should return 400 for invalid strategy."""
        with patch("tradingsystem.api.backtest.backtest_service") as mock_service:
            mock_service.run_backtest = AsyncMock(
                side_effect=ValueError("Strategy not found")
            )

            response = client.post(
                "/backtest",
                json={
                    "strategy_id": "unknown",
                    "instrument": "EUR_USD",
                    "start_date": "2024-01-01T00:00:00Z",
                    "end_date": "2024-01-31T00:00:00Z",
                },
            )

            assert response.status_code == 400

    def test_run_backtest_execution_error(self, client):
        """Should return 500 on execution error."""
        with patch("tradingsystem.api.backtest.backtest_service") as mock_service:
            mock_service.run_backtest = AsyncMock(
                side_effect=Exception("Database error")
            )

            response = client.post(
                "/backtest",
                json={
                    "strategy_id": "ma_crossover",
                    "instrument": "EUR_USD",
                    "start_date": "2024-01-01T00:00:00Z",
                    "end_date": "2024-01-31T00:00:00Z",
                },
            )

            assert response.status_code == 500


class TestListBacktests:
    """Tests for GET /backtest/history."""

    def test_list_backtests(self, client, sample_backtest_summary):
        """Should return backtest history."""
        with patch("tradingsystem.api.backtest.backtest_service") as mock_service:
            mock_service.list_backtests = AsyncMock(return_value=[sample_backtest_summary])

            response = client.get("/backtest/history")

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1

    def test_list_backtests_with_filters(self, client, sample_backtest_summary):
        """Should filter backtests by strategy and instrument."""
        with patch("tradingsystem.api.backtest.backtest_service") as mock_service:
            mock_service.list_backtests = AsyncMock(return_value=[sample_backtest_summary])

            response = client.get(
                "/backtest/history",
                params={
                    "strategy_id": "ma_crossover",
                    "instrument": "EUR_USD",
                    "limit": 25,
                },
            )

            assert response.status_code == 200
            mock_service.list_backtests.assert_called_once_with(
                strategy_id="ma_crossover",
                instrument="EUR_USD",
                limit=25,
                offset=0,
            )

    def test_list_backtests_empty(self, client):
        """Should return empty list when no backtests."""
        with patch("tradingsystem.api.backtest.backtest_service") as mock_service:
            mock_service.list_backtests = AsyncMock(return_value=[])

            response = client.get("/backtest/history")

            assert response.status_code == 200
            assert response.json() == []


class TestGetBacktest:
    """Tests for GET /backtest/{backtest_id}."""

    def test_get_backtest_found(self, client, sample_backtest_result):
        """Should return backtest when found."""
        with patch("tradingsystem.api.backtest.backtest_service") as mock_service:
            mock_service.get_backtest = AsyncMock(return_value=sample_backtest_result)

            response = client.get(f"/backtest/{sample_backtest_result.id}")

            assert response.status_code == 200
            data = response.json()
            assert data["id"] == str(sample_backtest_result.id)

    def test_get_backtest_not_found(self, client):
        """Should return 404 when backtest not found."""
        with patch("tradingsystem.api.backtest.backtest_service") as mock_service:
            mock_service.get_backtest = AsyncMock(return_value=None)

            response = client.get(f"/backtest/{uuid4()}")

            assert response.status_code == 404


class TestDeleteBacktest:
    """Tests for DELETE /backtest/{backtest_id}."""

    def test_delete_backtest_success(self, client):
        """Should delete backtest."""
        with patch("tradingsystem.api.backtest.backtest_service") as mock_service:
            mock_service.delete_backtest = AsyncMock(return_value=True)

            response = client.delete(f"/backtest/{uuid4()}")

            assert response.status_code == 204

    def test_delete_backtest_not_found(self, client):
        """Should return 404 when backtest not found."""
        with patch("tradingsystem.api.backtest.backtest_service") as mock_service:
            mock_service.delete_backtest = AsyncMock(return_value=False)

            response = client.delete(f"/backtest/{uuid4()}")

            assert response.status_code == 404


class TestGetBacktestTrades:
    """Tests for GET /backtest/{backtest_id}/trades."""

    def test_get_backtest_trades(self, client, sample_backtest_result):
        """Should return backtest trades."""
        with patch("tradingsystem.api.backtest.backtest_service") as mock_service:
            mock_service.get_backtest = AsyncMock(return_value=sample_backtest_result)

            response = client.get(f"/backtest/{sample_backtest_result.id}/trades")

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["side"] == "LONG"

    def test_get_backtest_trades_not_found(self, client):
        """Should return 404 when backtest not found."""
        with patch("tradingsystem.api.backtest.backtest_service") as mock_service:
            mock_service.get_backtest = AsyncMock(return_value=None)

            response = client.get(f"/backtest/{uuid4()}/trades")

            assert response.status_code == 404


class TestGetBacktestEquityCurve:
    """Tests for GET /backtest/{backtest_id}/equity-curve."""

    def test_get_equity_curve(self, client, sample_backtest_result):
        """Should return backtest equity curve."""
        with patch("tradingsystem.api.backtest.backtest_service") as mock_service:
            mock_service.get_backtest = AsyncMock(return_value=sample_backtest_result)

            response = client.get(f"/backtest/{sample_backtest_result.id}/equity-curve")

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2

    def test_get_equity_curve_not_found(self, client):
        """Should return 404 when backtest not found."""
        with patch("tradingsystem.api.backtest.backtest_service") as mock_service:
            mock_service.get_backtest = AsyncMock(return_value=None)

            response = client.get(f"/backtest/{uuid4()}/equity-curve")

            assert response.status_code == 404


class TestGetBacktestMetrics:
    """Tests for GET /backtest/{backtest_id}/metrics."""

    def test_get_metrics(self, client, sample_backtest_result):
        """Should return backtest metrics."""
        with patch("tradingsystem.api.backtest.backtest_service") as mock_service:
            mock_service.get_backtest = AsyncMock(return_value=sample_backtest_result)

            response = client.get(f"/backtest/{sample_backtest_result.id}/metrics")

            assert response.status_code == 200
            data = response.json()
            assert data["total_trades"] == 20
            assert float(data["win_rate"]) == 0.60

    def test_get_metrics_not_found(self, client):
        """Should return 404 when backtest not found."""
        with patch("tradingsystem.api.backtest.backtest_service") as mock_service:
            mock_service.get_backtest = AsyncMock(return_value=None)

            response = client.get(f"/backtest/{uuid4()}/metrics")

            assert response.status_code == 404
