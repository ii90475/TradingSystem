"""API tests for the Rates endpoints."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from tradingsystem.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def sample_current_rate():
    """Create sample current rate."""
    from tradingsystem.core.rateservice import CurrentRate

    return CurrentRate(
        pair="EUR_USD",
        bid=Decimal("1.08500"),
        ask=Decimal("1.08520"),
        time=datetime.now(timezone.utc),
        tradeable=True,
    )


class TestGetCurrentRate:
    """Tests for GET /rates/current/{pair}."""

    def test_get_current_rate_success(self, client, sample_current_rate):
        """Should return current rate for a pair."""
        with patch(
            "tradingsystem.api.rates.rateservice_client"
        ) as mock_client:
            mock_client.get_current_rate = AsyncMock(return_value=sample_current_rate)

            response = client.get("/rates/current/EUR_USD")

            assert response.status_code == 200
            data = response.json()
            assert data["pair"] == "EUR_USD"
            assert data["bid"] == "1.08500"
            assert data["ask"] == "1.08520"
            assert "mid" in data
            assert "spread" in data
            assert "age_seconds" in data
            assert data["tradeable"] is True

    def test_get_current_rate_calculates_mid(self, client, sample_current_rate):
        """Should calculate mid price correctly."""
        with patch(
            "tradingsystem.api.rates.rateservice_client"
        ) as mock_client:
            mock_client.get_current_rate = AsyncMock(return_value=sample_current_rate)

            response = client.get("/rates/current/EUR_USD")

            assert response.status_code == 200
            data = response.json()
            # Mid should be (1.08500 + 1.08520) / 2 = 1.08510
            assert data["mid"] == "1.08510"
            # Spread should be 1.08520 - 1.08500 = 0.00020
            assert data["spread"] == "0.00020"

    def test_get_current_rate_error(self, client):
        """Should return 400 on error."""
        with patch(
            "tradingsystem.api.rates.rateservice_client"
        ) as mock_client:
            mock_client.get_current_rate = AsyncMock(
                side_effect=Exception("RateService unavailable")
            )

            response = client.get("/rates/current/EUR_USD")

            assert response.status_code == 400
            assert "Failed to get rate" in response.json()["detail"]


class TestGetCurrentRates:
    """Tests for GET /rates/current."""

    def test_get_current_rates_all(self, client, sample_current_rate):
        """Should return all current rates."""
        from tradingsystem.core.rateservice import CurrentRate

        rates = [
            sample_current_rate,
            CurrentRate(
                pair="GBP_USD",
                bid=Decimal("1.26500"),
                ask=Decimal("1.26530"),
                time=datetime.now(timezone.utc),
                tradeable=True,
            ),
        ]

        with patch(
            "tradingsystem.api.rates.rateservice_client"
        ) as mock_client:
            mock_client.get_current_rates = AsyncMock(return_value=rates)

            response = client.get("/rates/current")

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            assert data[0]["pair"] == "EUR_USD"
            assert data[1]["pair"] == "GBP_USD"

    def test_get_current_rates_filtered(self, client, sample_current_rate):
        """Should filter by pairs."""
        with patch(
            "tradingsystem.api.rates.rateservice_client"
        ) as mock_client:
            mock_client.get_current_rates = AsyncMock(return_value=[sample_current_rate])

            response = client.get("/rates/current?pairs=EUR_USD")

            assert response.status_code == 200
            mock_client.get_current_rates.assert_called_once()

    def test_get_current_rates_error(self, client):
        """Should return 400 on error."""
        with patch(
            "tradingsystem.api.rates.rateservice_client"
        ) as mock_client:
            mock_client.get_current_rates = AsyncMock(
                side_effect=Exception("RateService unavailable")
            )

            response = client.get("/rates/current")

            assert response.status_code == 400
            assert "Failed to get rates" in response.json()["detail"]


class TestGetAvailablePairs:
    """Tests for GET /rates/pairs."""

    def test_get_pairs_success(self, client):
        """Should return available pairs."""
        pairs = ["EUR_USD", "GBP_USD", "USD_JPY"]

        with patch(
            "tradingsystem.api.rates.rateservice_client"
        ) as mock_client:
            mock_client.get_pairs = AsyncMock(return_value=pairs)

            response = client.get("/rates/pairs")

            assert response.status_code == 200
            data = response.json()
            assert data == pairs

    def test_get_pairs_error(self, client):
        """Should return 400 on error."""
        with patch(
            "tradingsystem.api.rates.rateservice_client"
        ) as mock_client:
            mock_client.get_pairs = AsyncMock(
                side_effect=Exception("RateService unavailable")
            )

            response = client.get("/rates/pairs")

            assert response.status_code == 400
            assert "Failed to get pairs" in response.json()["detail"]


class TestRatesApiPrefix:
    """Tests for /api/rates prefix."""

    def test_api_prefix_current_rate(self, client, sample_current_rate):
        """Should work with /api prefix."""
        with patch(
            "tradingsystem.api.rates.rateservice_client"
        ) as mock_client:
            mock_client.get_current_rate = AsyncMock(return_value=sample_current_rate)

            response = client.get("/api/rates/current/EUR_USD")

            assert response.status_code == 200
            assert response.json()["pair"] == "EUR_USD"

    def test_api_prefix_current_rates(self, client, sample_current_rate):
        """Should work with /api prefix for all rates."""
        with patch(
            "tradingsystem.api.rates.rateservice_client"
        ) as mock_client:
            mock_client.get_current_rates = AsyncMock(return_value=[sample_current_rate])

            response = client.get("/api/rates/current")

            assert response.status_code == 200

    def test_api_prefix_pairs(self, client):
        """Should work with /api prefix for pairs."""
        with patch(
            "tradingsystem.api.rates.rateservice_client"
        ) as mock_client:
            mock_client.get_pairs = AsyncMock(return_value=["EUR_USD"])

            response = client.get("/api/rates/pairs")

            assert response.status_code == 200
