"""Tests for WebSocket rate streaming."""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tradingsystem.core.websocket_manager import RateConnectionManager
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


class TestWebSocketStatus:
    """Tests for GET /rates/ws/status."""

    def test_get_websocket_status(self, client):
        """Should return WebSocket status."""
        response = client.get("/rates/ws/status")

        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data
        assert "poll_interval_ms" in data
        assert "active_connections" in data
        assert "broadcaster_running" in data

    def test_get_websocket_status_api_prefix(self, client):
        """Should work with /api prefix."""
        response = client.get("/api/rates/ws/status")

        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data


class TestRateConnectionManager:
    """Tests for RateConnectionManager."""

    @pytest.fixture
    def manager(self):
        """Create a fresh connection manager."""
        return RateConnectionManager()

    @pytest.mark.asyncio
    async def test_connect_adds_connection(self, manager):
        """Should add WebSocket to active connections."""
        mock_ws = AsyncMock()

        await manager.connect(mock_ws)

        assert mock_ws in manager.active_connections
        assert manager.connection_count == 1
        mock_ws.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_removes_connection(self, manager):
        """Should remove WebSocket from active connections."""
        mock_ws = AsyncMock()
        await manager.connect(mock_ws)

        manager.disconnect(mock_ws)

        assert mock_ws not in manager.active_connections
        assert manager.connection_count == 0

    @pytest.mark.asyncio
    async def test_disconnect_handles_missing_connection(self, manager):
        """Should handle disconnecting non-existent connection."""
        mock_ws = AsyncMock()

        # Should not raise
        manager.disconnect(mock_ws)

        assert manager.connection_count == 0

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_all(self, manager):
        """Should broadcast message to all connected clients."""
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        await manager.connect(ws1)
        await manager.connect(ws2)

        message = {"type": "test", "data": "hello"}
        await manager.broadcast(message)

        ws1.send_json.assert_called_once_with(message)
        ws2.send_json.assert_called_once_with(message)

    @pytest.mark.asyncio
    async def test_broadcast_no_connections(self, manager):
        """Should handle broadcast with no connections."""
        message = {"type": "test", "data": "hello"}

        # Should not raise
        await manager.broadcast(message)

    @pytest.mark.asyncio
    async def test_broadcast_removes_failed_connections(self, manager):
        """Should remove connections that fail to receive."""
        ws_good = AsyncMock()
        ws_bad = AsyncMock()
        ws_bad.send_json.side_effect = Exception("Connection closed")

        await manager.connect(ws_good)
        await manager.connect(ws_bad)
        assert manager.connection_count == 2

        await manager.broadcast({"type": "test"})

        # Bad connection should be removed
        assert manager.connection_count == 1
        assert ws_good in manager.active_connections
        assert ws_bad not in manager.active_connections

    @pytest.mark.asyncio
    async def test_start_stop_broadcasting(self, manager):
        """Should start and stop broadcasting task."""
        assert not manager.is_running

        await manager.start_broadcasting()
        assert manager.is_running

        await manager.stop_broadcasting()
        assert not manager.is_running

    @pytest.mark.asyncio
    async def test_start_broadcasting_idempotent(self, manager):
        """Should not start multiple broadcast tasks."""
        await manager.start_broadcasting()
        task1 = manager._broadcast_task

        await manager.start_broadcasting()
        task2 = manager._broadcast_task

        assert task1 is task2

        await manager.stop_broadcasting()


class TestWebSocketEndpoint:
    """Tests for WebSocket endpoint behavior."""

    def test_websocket_status_shows_config(self, client):
        """Should show configured poll interval."""
        with patch("tradingsystem.api.rates.settings") as mock_settings:
            mock_settings.ws_enabled = True
            mock_settings.ws_rate_poll_interval_ms = 500

            response = client.get("/rates/ws/status")

            assert response.status_code == 200


class TestWebSocketBroadcast:
    """Tests for broadcast functionality."""

    @pytest.mark.asyncio
    async def test_broadcast_formats_rates_correctly(self):
        """Should format rates correctly for broadcast."""
        from tradingsystem.core.rateservice import CurrentRate

        manager = RateConnectionManager()
        mock_ws = AsyncMock()
        await manager.connect(mock_ws)

        # Create test rate data
        now = datetime.now(timezone.utc)
        rate_data = [{
            "pair": "EUR_USD",
            "bid": "1.08500",
            "ask": "1.08520",
            "mid": "1.08510",
            "spread": "0.00020",
            "time": now.isoformat(),
            "age_seconds": 0.5,
            "tradeable": True,
        }]

        message = {
            "type": "rates",
            "timestamp": now.isoformat(),
            "data": rate_data,
        }

        await manager.broadcast(message)

        # Check broadcast was called with correct format
        assert mock_ws.send_json.called
        call_args = mock_ws.send_json.call_args[0][0]
        assert call_args["type"] == "rates"
        assert len(call_args["data"]) == 1
        assert call_args["data"][0]["pair"] == "EUR_USD"
        assert call_args["data"][0]["mid"] == "1.08510"
