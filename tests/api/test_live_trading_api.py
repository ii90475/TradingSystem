"""API tests for the Live Trading endpoints."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from tradingsystem.main import app
from tradingsystem.models.order import Order, OrderSide, OrderStatus, OrderType
from tradingsystem.models.position import Position, PositionSide, PositionStatus
from tradingsystem.core.oanda_trading import OandaAccount, OandaOrderResponse, OandaTrade
from tradingsystem.services.risk_manager import RiskViolation


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def sample_order():
    """Create a sample order for testing."""
    return Order(
        id=uuid4(),
        external_id="oanda-12345",
        strategy_id="test_strategy",
        instrument="EUR_USD",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("1000"),
        price=None,
        status=OrderStatus.FILLED,
        created_at=datetime.now(timezone.utc),
        filled_at=datetime.now(timezone.utc),
        filled_price=Decimal("1.0850"),
        filled_quantity=Decimal("1000"),
    )


@pytest.fixture
def sample_position():
    """Create a sample position for testing."""
    return Position(
        id=uuid4(),
        instrument="EUR_USD",
        side=PositionSide.LONG,
        quantity=Decimal("1000"),
        entry_price=Decimal("1.0850"),
        entry_time=datetime.now(timezone.utc),
        exit_price=None,
        exit_time=None,
        status=PositionStatus.OPEN,
        strategy_id="test_strategy",
        pnl=None,
        pnl_percent=None,
    )


@pytest.fixture
def mock_oanda_response():
    """Create mock OANDA order response."""
    return OandaOrderResponse(
        order_id="oanda-order-123",
        trade_id="oanda-trade-456",
        instrument="EUR_USD",
        units=Decimal("1000"),
        price=Decimal("1.0850"),
        time=datetime.now(timezone.utc),
        state="FILLED",
    )


@pytest.fixture
def mock_oanda_account():
    """Create mock OANDA account."""
    return OandaAccount(
        id="001-001-12345-001",
        balance=Decimal("10000.00"),
        nav=Decimal("10050.00"),
        unrealized_pnl=Decimal("50.00"),
        margin_used=Decimal("500.00"),
        margin_available=Decimal("9500.00"),
        open_trade_count=2,
        open_position_count=2,
    )


@pytest.fixture
def mock_oanda_trade():
    """Create mock OANDA trade."""
    return OandaTrade(
        id="trade-123",
        instrument="EUR_USD",
        units=Decimal("1000"),
        price=Decimal("1.0850"),
        unrealized_pnl=Decimal("25.00"),
        state="OPEN",
        open_time=datetime.now(timezone.utc),
    )


class TestTradingMode:
    """Tests for GET/POST /live/mode."""

    def test_get_trading_mode(self, client):
        """Should return current trading mode."""
        with patch("tradingsystem.api.live_trading.oanda_trading_client") as mock_client, \
             patch("tradingsystem.api.live_trading.settings") as mock_settings:
            mock_client.trading_mode = "PAPER"
            mock_settings.live_trading_enabled = False

            response = client.get("/live/mode")

            assert response.status_code == 200
            data = response.json()
            assert data["mode"] == "PAPER"

    def test_set_mode_to_paper(self, client):
        """Should switch to PAPER mode."""
        with patch("tradingsystem.api.live_trading.oanda_trading_client") as mock_client:
            mock_client.trading_mode = "PAPER"

            response = client.post(
                "/live/mode",
                json={"mode": "PAPER"},
            )

            assert response.status_code == 200
            mock_client.set_trading_mode.assert_called_once_with("PAPER")

    def test_set_mode_to_live_requires_confirm(self, client):
        """Should reject LIVE mode without confirm_live."""
        with patch("tradingsystem.api.live_trading.settings") as mock_settings:
            mock_settings.live_trading_enabled = True

            response = client.post(
                "/live/mode",
                json={"mode": "LIVE", "confirm_live": False},
            )

            assert response.status_code == 400
            assert "confirm_live" in response.json()["detail"]

    def test_set_mode_to_live_requires_enabled(self, client):
        """Should reject LIVE mode when live trading disabled."""
        with patch("tradingsystem.api.live_trading.settings") as mock_settings:
            mock_settings.live_trading_enabled = False

            response = client.post(
                "/live/mode",
                json={"mode": "LIVE", "confirm_live": True},
            )

            assert response.status_code == 403

    def test_set_mode_to_live_success(self, client):
        """Should switch to LIVE mode with confirmation and enabled."""
        with patch("tradingsystem.api.live_trading.oanda_trading_client") as mock_client, \
             patch("tradingsystem.api.live_trading.settings") as mock_settings:
            mock_settings.live_trading_enabled = True
            mock_client.trading_mode = "LIVE"

            response = client.post(
                "/live/mode",
                json={"mode": "LIVE", "confirm_live": True},
            )

            assert response.status_code == 200
            mock_client.set_trading_mode.assert_called_once_with("LIVE")

    def test_set_mode_invalid(self, client):
        """Should reject invalid mode."""
        response = client.post(
            "/live/mode",
            json={"mode": "INVALID"},
        )

        assert response.status_code == 400


class TestGetLiveStatus:
    """Tests for GET /live/status."""

    def test_get_live_status(self, client):
        """Should return live trading status."""
        status_data = {
            "live_trading_enabled": True,
            "account_connected": True,
            "risk_status": "OK",
            "open_positions": 2,
        }

        with patch("tradingsystem.api.live_trading.live_trading_service") as mock_service:
            mock_service.get_live_account_status = AsyncMock(return_value=status_data)

            response = client.get("/live/status")

            assert response.status_code == 200
            data = response.json()
            assert "live_trading_enabled" in data


class TestGetAccountSummary:
    """Tests for GET /live/account."""

    def test_get_account_success(self, client, mock_oanda_account):
        """Should return OANDA account summary."""
        with patch("tradingsystem.api.live_trading.oanda_trading_client") as mock_client:
            mock_client.get_account_summary = AsyncMock(return_value=mock_oanda_account)

            response = client.get("/live/account")

            assert response.status_code == 200
            data = response.json()
            assert data["balance"] == "10000.00"
            assert data["nav"] == "10050.00"

    def test_get_account_error(self, client):
        """Should return 400 on OANDA error."""
        with patch("tradingsystem.api.live_trading.oanda_trading_client") as mock_client:
            mock_client.get_account_summary = AsyncMock(
                side_effect=Exception("Connection failed")
            )

            response = client.get("/live/account")

            assert response.status_code == 400


class TestGetOpenTrades:
    """Tests for GET /live/trades."""

    def test_get_open_trades(self, client, mock_oanda_trade):
        """Should return open OANDA trades."""
        with patch("tradingsystem.api.live_trading.oanda_trading_client") as mock_client:
            mock_client.get_open_trades = AsyncMock(return_value=[mock_oanda_trade])

            response = client.get("/live/trades")

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["instrument"] == "EUR_USD"

    def test_get_open_trades_empty(self, client):
        """Should return empty list when no trades."""
        with patch("tradingsystem.api.live_trading.oanda_trading_client") as mock_client:
            mock_client.get_open_trades = AsyncMock(return_value=[])

            response = client.get("/live/trades")

            assert response.status_code == 200
            assert response.json() == []

    def test_get_open_trades_error(self, client):
        """Should return 400 on OANDA error."""
        with patch("tradingsystem.api.live_trading.oanda_trading_client") as mock_client:
            mock_client.get_open_trades = AsyncMock(
                side_effect=Exception("Failed to fetch trades")
            )

            response = client.get("/live/trades")

            assert response.status_code == 400
            assert "Failed to fetch trades" in response.json()["detail"]


class TestExecuteLiveTrade:
    """Tests for POST /live/trade."""

    def test_execute_trade_disabled(self, client):
        """Should return 403 when in LIVE mode with live trading disabled."""
        with patch("tradingsystem.api.live_trading.oanda_trading_client") as mock_client, \
             patch("tradingsystem.api.live_trading.settings") as mock_settings:
            mock_client.trading_mode = "LIVE"
            mock_settings.live_trading_enabled = False

            response = client.post(
                "/live/trade",
                json={
                    "instrument": "EUR_USD",
                    "side": "BUY",
                    "quantity": "1000",
                },
            )

            assert response.status_code == 403
            assert "disabled" in response.json()["detail"].lower()

    def test_execute_trade_success(
        self, client, sample_order, sample_position, mock_oanda_response
    ):
        """Should execute trade when in PAPER mode."""
        with patch("tradingsystem.api.live_trading.oanda_trading_client") as mock_client, \
             patch("tradingsystem.api.live_trading.live_trading_service") as mock_service:
            mock_client.trading_mode = "PAPER"
            mock_service.execute_live_trade = AsyncMock(
                return_value=(sample_order, sample_position, mock_oanda_response)
            )

            response = client.post(
                "/live/trade",
                json={
                    "instrument": "EUR_USD",
                    "side": "BUY",
                    "quantity": "1000",
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert "order" in data
            assert "position" in data
            assert "oanda_order_id" in data

    def test_execute_trade_with_stops(
        self, client, sample_order, sample_position, mock_oanda_response
    ):
        """Should pass stop loss and take profit to service."""
        with patch("tradingsystem.api.live_trading.oanda_trading_client") as mock_client, \
             patch("tradingsystem.api.live_trading.live_trading_service") as mock_service:
            mock_client.trading_mode = "PAPER"
            mock_service.execute_live_trade = AsyncMock(
                return_value=(sample_order, sample_position, mock_oanda_response)
            )

            response = client.post(
                "/live/trade",
                json={
                    "instrument": "EUR_USD",
                    "side": "BUY",
                    "quantity": "1000",
                    "stop_loss": "1.0800",
                    "take_profit": "1.0950",
                },
            )

            assert response.status_code == 200
            mock_service.execute_live_trade.assert_called_once()
            call_kwargs = mock_service.execute_live_trade.call_args[1]
            assert call_kwargs["stop_loss"] == Decimal("1.0800")
            assert call_kwargs["take_profit"] == Decimal("1.0950")

    def test_execute_trade_risk_violation(self, client):
        """Should return 400 on risk violation."""
        from tradingsystem.services.live_trading_service import LiveTradingError

        with patch("tradingsystem.api.live_trading.oanda_trading_client") as mock_client, \
             patch("tradingsystem.api.live_trading.live_trading_service") as mock_service:
            mock_client.trading_mode = "PAPER"
            mock_service.execute_live_trade = AsyncMock(
                side_effect=LiveTradingError("Risk check failed: daily loss limit exceeded")
            )

            response = client.post(
                "/live/trade",
                json={
                    "instrument": "EUR_USD",
                    "side": "BUY",
                    "quantity": "1000",
                },
            )

            assert response.status_code == 400
            assert "risk" in response.json()["detail"].lower()

    def test_execute_trade_general_exception(self, client):
        """Should return 500 on unexpected error."""
        with patch("tradingsystem.api.live_trading.oanda_trading_client") as mock_client, \
             patch("tradingsystem.api.live_trading.live_trading_service") as mock_service:
            mock_client.trading_mode = "PAPER"
            mock_service.execute_live_trade = AsyncMock(
                side_effect=Exception("Unexpected database error")
            )

            response = client.post(
                "/live/trade",
                json={
                    "instrument": "EUR_USD",
                    "side": "BUY",
                    "quantity": "1000",
                },
            )

            assert response.status_code == 500
            assert "Trade execution failed" in response.json()["detail"]


class TestCloseLiveTrade:
    """Tests for POST /live/trade/{position_id}/close."""

    def test_close_trade_disabled(self, client):
        """Should return 403 when in LIVE mode with live trading disabled."""
        with patch("tradingsystem.api.live_trading.oanda_trading_client") as mock_client, \
             patch("tradingsystem.api.live_trading.settings") as mock_settings:
            mock_client.trading_mode = "LIVE"
            mock_settings.live_trading_enabled = False

            response = client.post(f"/live/trade/{uuid4()}/close")

            assert response.status_code == 403

    def test_close_trade_success(
        self, client, sample_order, sample_position, mock_oanda_response
    ):
        """Should close trade."""
        sample_position.status = PositionStatus.CLOSED
        sample_position.pnl = Decimal("50.00")

        with patch("tradingsystem.api.live_trading.oanda_trading_client") as mock_client, \
             patch("tradingsystem.api.live_trading.live_trading_service") as mock_service:
            mock_client.trading_mode = "PAPER"
            mock_service.close_live_trade = AsyncMock(
                return_value=(sample_order, sample_position, mock_oanda_response)
            )

            response = client.post(f"/live/trade/{sample_position.id}/close")

            assert response.status_code == 200
            data = response.json()
            assert data["pnl"] == "50.00"

    def test_close_trade_live_trading_error(self, client):
        """Should return 400 on LiveTradingError."""
        from tradingsystem.services.live_trading_service import LiveTradingError

        with patch("tradingsystem.api.live_trading.oanda_trading_client") as mock_client, \
             patch("tradingsystem.api.live_trading.live_trading_service") as mock_service:
            mock_client.trading_mode = "PAPER"
            mock_service.close_live_trade = AsyncMock(
                side_effect=LiveTradingError("Position not found in OANDA")
            )

            response = client.post(f"/live/trade/{uuid4()}/close")

            assert response.status_code == 400
            assert "Position not found" in response.json()["detail"]

    def test_close_trade_general_exception(self, client):
        """Should return 500 on unexpected error."""
        with patch("tradingsystem.api.live_trading.oanda_trading_client") as mock_client, \
             patch("tradingsystem.api.live_trading.live_trading_service") as mock_service:
            mock_client.trading_mode = "PAPER"
            mock_service.close_live_trade = AsyncMock(
                side_effect=Exception("Network timeout")
            )

            response = client.post(f"/live/trade/{uuid4()}/close")

            assert response.status_code == 500
            assert "Close failed" in response.json()["detail"]


class TestEmergencyCloseAll:
    """Tests for POST /live/emergency-close."""

    def test_emergency_close_disabled(self, client):
        """Should return 403 when in LIVE mode with live trading disabled."""
        with patch("tradingsystem.api.live_trading.oanda_trading_client") as mock_client, \
             patch("tradingsystem.api.live_trading.settings") as mock_settings:
            mock_client.trading_mode = "LIVE"
            mock_settings.live_trading_enabled = False

            response = client.post("/live/emergency-close")

            assert response.status_code == 403

    def test_emergency_close_success(self, client):
        """Should close all trades."""
        with patch("tradingsystem.api.live_trading.oanda_trading_client") as mock_client, \
             patch("tradingsystem.api.live_trading.live_trading_service") as mock_service:
            mock_client.trading_mode = "PAPER"
            mock_service.emergency_close_all = AsyncMock(
                return_value=[{"trade_id": "123", "pnl": "50.00"}]
            )

            response = client.post("/live/emergency-close")

            assert response.status_code == 200
            data = response.json()
            assert data["closed_count"] == 1

    def test_emergency_close_live_trading_error(self, client):
        """Should return 400 on LiveTradingError."""
        from tradingsystem.services.live_trading_service import LiveTradingError

        with patch("tradingsystem.api.live_trading.oanda_trading_client") as mock_client, \
             patch("tradingsystem.api.live_trading.live_trading_service") as mock_service:
            mock_client.trading_mode = "PAPER"
            mock_service.emergency_close_all = AsyncMock(
                side_effect=LiveTradingError("Failed to close all positions")
            )

            response = client.post("/live/emergency-close")

            assert response.status_code == 400
            assert "Failed to close all positions" in response.json()["detail"]


class TestCheckTradeRisk:
    """Tests for POST /live/risk/check."""

    def test_risk_check_approved(self, client):
        """Should return approval when risk checks pass."""
        mock_result = MagicMock()
        mock_result.approved = True
        mock_result.violations = []
        mock_result.messages = []

        with patch("tradingsystem.api.live_trading.risk_manager") as mock_rm:
            mock_rm.check_trade = AsyncMock(return_value=mock_result)

            response = client.post(
                "/live/risk/check",
                json={
                    "instrument": "EUR_USD",
                    "side": "BUY",
                    "quantity": "1000",
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["approved"] is True
            assert data["violations"] == []

    def test_risk_check_rejected(self, client):
        """Should return violations when risk checks fail."""
        mock_result = MagicMock()
        mock_result.approved = False
        mock_result.violations = [RiskViolation.MAX_DAILY_LOSS]
        mock_result.messages = ["Daily loss limit exceeded"]

        with patch("tradingsystem.api.live_trading.risk_manager") as mock_rm:
            mock_rm.check_trade = AsyncMock(return_value=mock_result)

            response = client.post(
                "/live/risk/check",
                json={
                    "instrument": "EUR_USD",
                    "side": "BUY",
                    "quantity": "1000",
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["approved"] is False
            assert len(data["violations"]) > 0


class TestGetRiskStatus:
    """Tests for GET /live/risk/status."""

    def test_get_risk_status(self, client):
        """Should return current risk status."""
        risk_data = {
            "circuit_breaker_active": False,
            "consecutive_losses": 0,
            "daily_loss_pct": 0.5,
            "open_positions": 2,
        }

        with patch("tradingsystem.api.live_trading.risk_manager") as mock_rm:
            mock_rm.get_risk_status.return_value = risk_data

            response = client.get("/live/risk/status")

            assert response.status_code == 200
            data = response.json()
            assert "circuit_breaker_active" in data


class TestResetCircuitBreaker:
    """Tests for POST /live/risk/reset-circuit-breaker."""

    def test_reset_circuit_breaker(self, client):
        """Should reset circuit breaker."""
        with patch("tradingsystem.api.live_trading.risk_manager") as mock_rm:
            mock_rm.reset_circuit_breaker.return_value = None
            mock_rm.get_risk_status.return_value = {
                "circuit_breaker_active": False,
                "consecutive_losses": 0,
            }

            response = client.post("/live/risk/reset-circuit-breaker")

            assert response.status_code == 200
            mock_rm.reset_circuit_breaker.assert_called_once()


class TestReconcilePositions:
    """Tests for GET /live/reconciliation."""

    def test_reconcile_positions(self, client):
        """Should return reconciliation results."""
        mock_result = MagicMock()
        mock_result.timestamp = datetime.now(timezone.utc)
        mock_result.oanda_positions = 2
        mock_result.local_positions = 2
        mock_result.in_sync = True
        mock_result.discrepancies = []

        with patch("tradingsystem.api.live_trading.reconciliation_service") as mock_service:
            mock_service.reconcile_positions = AsyncMock(return_value=mock_result)

            response = client.get("/live/reconciliation")

            assert response.status_code == 200
            data = response.json()
            assert data["in_sync"] is True

    def test_reconcile_positions_error(self, client):
        """Should return 400 on reconciliation error."""
        with patch("tradingsystem.api.live_trading.reconciliation_service") as mock_service:
            mock_service.reconcile_positions = AsyncMock(
                side_effect=Exception("OANDA API unavailable")
            )

            response = client.get("/live/reconciliation")

            assert response.status_code == 400
            assert "OANDA API unavailable" in response.json()["detail"]


class TestSyncPositions:
    """Tests for POST /live/reconciliation/sync."""

    def test_sync_positions(self, client):
        """Should sync positions from OANDA."""
        sync_result = {
            "synced": True,
            "positions_closed": 0,
            "positions_created": 0,
        }

        with patch("tradingsystem.api.live_trading.reconciliation_service") as mock_service:
            mock_service.sync_from_oanda = AsyncMock(return_value=sync_result)

            response = client.post("/live/reconciliation/sync")

            assert response.status_code == 200

    def test_sync_positions_error(self, client):
        """Should return 400 on sync error."""
        with patch("tradingsystem.api.live_trading.reconciliation_service") as mock_service:
            mock_service.sync_from_oanda = AsyncMock(
                side_effect=Exception("Failed to sync with OANDA")
            )

            response = client.post("/live/reconciliation/sync")

            assert response.status_code == 400
            assert "Failed to sync" in response.json()["detail"]


class TestGetOandaPositions:
    """Tests for GET /live/oanda/positions."""

    def test_get_oanda_positions(self, client):
        """Should return OANDA positions summary."""
        positions_data = {
            "positions": [
                {"instrument": "EUR_USD", "units": "1000", "unrealized_pnl": "25.00"}
            ]
        }

        with patch("tradingsystem.api.live_trading.reconciliation_service") as mock_service:
            mock_service.get_oanda_positions_summary = AsyncMock(return_value=positions_data)

            response = client.get("/live/oanda/positions")

            assert response.status_code == 200
