"""Unit tests for the Risk Manager service."""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from tradingsystem.models.order import OrderSide
from tradingsystem.services.risk_manager import (
    RiskManager,
    RiskViolation,
    RiskCheckResult,
    DailyStats,
)


class TestRiskManagerCheckTrade:
    """Tests for RiskManager.check_trade() method."""

    @pytest.fixture
    def risk_manager(self):
        """Create a fresh RiskManager instance for each test."""
        return RiskManager()

    @pytest.fixture
    def mock_account(self, mock_oanda_account):
        """Create a mock OANDA account."""
        return mock_oanda_account(
            balance=Decimal("10000.00"),
            open_trade_count=2,
        )

    @pytest.mark.asyncio
    async def test_live_trading_disabled_returns_violation(self, risk_manager):
        """When live trading is disabled, should return LIVE_TRADING_DISABLED violation."""
        with patch("tradingsystem.services.risk_manager.settings") as mock_settings:
            mock_settings.live_trading_enabled = False

            result = await risk_manager.check_trade(
                instrument="EUR_USD",
                side=OrderSide.BUY,
                quantity=Decimal("1000"),
            )

            assert result.approved is False
            assert RiskViolation.LIVE_TRADING_DISABLED in result.violations
            assert "Live trading is disabled" in result.messages[0]

    @pytest.mark.asyncio
    async def test_max_position_size_violation(self, risk_manager, mock_account):
        """When quantity exceeds max position size, should return violation."""
        with patch("tradingsystem.services.risk_manager.settings") as mock_settings, \
             patch("tradingsystem.services.risk_manager.oanda_trading_client") as mock_oanda:

            mock_settings.live_trading_enabled = True
            mock_settings.max_position_size_pct = 5.0  # 5% of 10000 = 500
            mock_settings.max_daily_loss_pct = 2.0
            mock_settings.max_open_positions = 10

            mock_oanda.get_account_summary = AsyncMock(return_value=mock_account)
            mock_oanda.get_open_trades = AsyncMock(return_value=[])

            # Request 1000 units, but max is 500 (5% of 10000)
            result = await risk_manager.check_trade(
                instrument="EUR_USD",
                side=OrderSide.BUY,
                quantity=Decimal("1000"),
            )

            assert result.approved is False
            assert RiskViolation.MAX_POSITION_SIZE in result.violations

    @pytest.mark.asyncio
    async def test_max_position_size_within_limit(self, risk_manager, mock_account):
        """When quantity is within max position size, should not have violation."""
        with patch("tradingsystem.services.risk_manager.settings") as mock_settings, \
             patch("tradingsystem.services.risk_manager.oanda_trading_client") as mock_oanda:

            mock_settings.live_trading_enabled = True
            mock_settings.max_position_size_pct = 5.0  # 5% of 10000 = 500
            mock_settings.max_daily_loss_pct = 2.0
            mock_settings.max_open_positions = 10

            mock_oanda.get_account_summary = AsyncMock(return_value=mock_account)
            mock_oanda.get_open_trades = AsyncMock(return_value=[])

            # Request 400 units, max is 500
            result = await risk_manager.check_trade(
                instrument="EUR_USD",
                side=OrderSide.BUY,
                quantity=Decimal("400"),
            )

            assert RiskViolation.MAX_POSITION_SIZE not in result.violations

    @pytest.mark.asyncio
    async def test_max_open_positions_violation(self, risk_manager, mock_account, mock_oanda_trade):
        """When at max open positions, should return violation."""
        with patch("tradingsystem.services.risk_manager.settings") as mock_settings, \
             patch("tradingsystem.services.risk_manager.oanda_trading_client") as mock_oanda:

            mock_settings.live_trading_enabled = True
            mock_settings.max_position_size_pct = 50.0
            mock_settings.max_daily_loss_pct = 2.0
            mock_settings.max_open_positions = 3

            mock_oanda.get_account_summary = AsyncMock(return_value=mock_account)
            # Already have 3 trades open (at the limit)
            mock_oanda.get_open_trades = AsyncMock(return_value=[
                mock_oanda_trade(),
                mock_oanda_trade(),
                mock_oanda_trade(),
            ])

            result = await risk_manager.check_trade(
                instrument="EUR_USD",
                side=OrderSide.BUY,
                quantity=Decimal("100"),
            )

            assert result.approved is False
            assert RiskViolation.MAX_OPEN_POSITIONS in result.violations

    @pytest.mark.asyncio
    async def test_max_daily_loss_violation(self, risk_manager, mock_oanda_account):
        """When daily loss limit is reached, should return violation."""
        # Account started at 10000, now at 9700 (3% loss, limit is 2%)
        current_account = mock_oanda_account(balance=Decimal("9700.00"))

        with patch("tradingsystem.services.risk_manager.settings") as mock_settings, \
             patch("tradingsystem.services.risk_manager.oanda_trading_client") as mock_oanda:

            mock_settings.live_trading_enabled = True
            mock_settings.max_position_size_pct = 50.0
            mock_settings.max_daily_loss_pct = 2.0  # 2% of 10000 = 200 max loss
            mock_settings.max_open_positions = 10

            mock_oanda.get_account_summary = AsyncMock(return_value=current_account)
            mock_oanda.get_open_trades = AsyncMock(return_value=[])

            # Initialize daily stats with starting balance
            risk_manager._daily_stats = DailyStats(
                date=date.today(),
                starting_balance=Decimal("10000.00"),
                current_balance=Decimal("9700.00"),
                realized_pnl=Decimal("-300.00"),
                trades_count=3,
                consecutive_losses=0,
            )

            result = await risk_manager.check_trade(
                instrument="EUR_USD",
                side=OrderSide.BUY,
                quantity=Decimal("100"),
            )

            assert result.approved is False
            assert RiskViolation.MAX_DAILY_LOSS in result.violations

    @pytest.mark.asyncio
    async def test_consecutive_losses_circuit_breaker(self, mock_account):
        """When circuit breaker is triggered, should return violation."""
        # Create a fresh risk manager for this test
        risk_manager = RiskManager()

        with patch("tradingsystem.services.risk_manager.settings") as mock_settings, \
             patch("tradingsystem.services.risk_manager.oanda_trading_client") as mock_oanda:

            mock_settings.live_trading_enabled = True
            mock_settings.max_position_size_pct = 50.0
            mock_settings.max_daily_loss_pct = 10.0
            mock_settings.max_open_positions = 10

            mock_oanda.get_account_summary = AsyncMock(return_value=mock_account)
            mock_oanda.get_open_trades = AsyncMock(return_value=[])

            # Must set daily_stats for today to prevent _update_daily_stats
            # from resetting consecutive_losses
            risk_manager._daily_stats = DailyStats(
                date=date.today(),
                starting_balance=Decimal("10000.00"),
                current_balance=Decimal("10000.00"),
                realized_pnl=Decimal("0"),
                trades_count=5,
                consecutive_losses=5,
            )

            # Simulate 5 consecutive losses (circuit breaker threshold)
            risk_manager._consecutive_losses = 5
            risk_manager._max_consecutive_losses = 5

            result = await risk_manager.check_trade(
                instrument="EUR_USD",
                side=OrderSide.BUY,
                quantity=Decimal("100"),
            )

            assert result.approved is False
            assert RiskViolation.CONSECUTIVE_LOSSES in result.violations

    @pytest.mark.asyncio
    async def test_all_checks_pass(self, risk_manager, mock_account):
        """When all checks pass, should approve the trade."""
        with patch("tradingsystem.services.risk_manager.settings") as mock_settings, \
             patch("tradingsystem.services.risk_manager.oanda_trading_client") as mock_oanda:

            mock_settings.live_trading_enabled = True
            mock_settings.max_position_size_pct = 50.0
            mock_settings.max_daily_loss_pct = 10.0
            mock_settings.max_open_positions = 10

            mock_oanda.get_account_summary = AsyncMock(return_value=mock_account)
            mock_oanda.get_open_trades = AsyncMock(return_value=[])

            result = await risk_manager.check_trade(
                instrument="EUR_USD",
                side=OrderSide.BUY,
                quantity=Decimal("100"),
            )

            assert result.approved is True
            assert len(result.violations) == 0

    @pytest.mark.asyncio
    async def test_multiple_violations(self, risk_manager, mock_oanda_account, mock_oanda_trade):
        """When multiple violations occur, should return all of them."""
        # Account at loss limit
        current_account = mock_oanda_account(balance=Decimal("9700.00"))

        with patch("tradingsystem.services.risk_manager.settings") as mock_settings, \
             patch("tradingsystem.services.risk_manager.oanda_trading_client") as mock_oanda:

            mock_settings.live_trading_enabled = True
            mock_settings.max_position_size_pct = 5.0  # Max 500
            mock_settings.max_daily_loss_pct = 2.0
            mock_settings.max_open_positions = 2

            mock_oanda.get_account_summary = AsyncMock(return_value=current_account)
            mock_oanda.get_open_trades = AsyncMock(return_value=[
                mock_oanda_trade(),
                mock_oanda_trade(),
            ])

            # Set up daily stats showing loss
            risk_manager._daily_stats = DailyStats(
                date=date.today(),
                starting_balance=Decimal("10000.00"),
                current_balance=Decimal("9700.00"),
                realized_pnl=Decimal("-300.00"),
                trades_count=3,
                consecutive_losses=0,
            )

            # Request too large position (1000 > 500 max)
            result = await risk_manager.check_trade(
                instrument="EUR_USD",
                side=OrderSide.BUY,
                quantity=Decimal("1000"),
            )

            assert result.approved is False
            # Should have multiple violations
            assert RiskViolation.MAX_POSITION_SIZE in result.violations
            assert RiskViolation.MAX_OPEN_POSITIONS in result.violations
            assert RiskViolation.MAX_DAILY_LOSS in result.violations

    @pytest.mark.asyncio
    async def test_account_fetch_failure(self, risk_manager):
        """When OANDA account fetch fails, should reject trade."""
        with patch("tradingsystem.services.risk_manager.settings") as mock_settings, \
             patch("tradingsystem.services.risk_manager.oanda_trading_client") as mock_oanda:

            mock_settings.live_trading_enabled = True
            mock_oanda.get_account_summary = AsyncMock(
                side_effect=Exception("OANDA API error")
            )

            result = await risk_manager.check_trade(
                instrument="EUR_USD",
                side=OrderSide.BUY,
                quantity=Decimal("100"),
            )

            assert result.approved is False
            assert "Failed to get account" in result.messages[0]


class TestRiskManagerTradeTracking:
    """Tests for trade result tracking methods."""

    @pytest.fixture
    def risk_manager(self):
        """Create a fresh RiskManager instance for each test."""
        return RiskManager()

    def test_record_loss_increments_consecutive_losses(self, risk_manager):
        """Recording a loss should increment consecutive losses."""
        risk_manager._consecutive_losses = 2

        risk_manager.record_trade_result(Decimal("-50.00"))

        assert risk_manager._consecutive_losses == 3

    def test_record_win_resets_consecutive_losses(self, risk_manager):
        """Recording a win should reset consecutive losses to 0."""
        risk_manager._consecutive_losses = 3

        risk_manager.record_trade_result(Decimal("50.00"))

        assert risk_manager._consecutive_losses == 0

    def test_record_zero_profit_resets_consecutive_losses(self, risk_manager):
        """Recording zero profit (breakeven) should reset consecutive losses."""
        risk_manager._consecutive_losses = 3

        risk_manager.record_trade_result(Decimal("0.00"))

        assert risk_manager._consecutive_losses == 0

    def test_record_trade_updates_daily_stats(self, risk_manager):
        """Recording a trade should update daily stats."""
        risk_manager._daily_stats = DailyStats(
            date=date.today(),
            starting_balance=Decimal("10000.00"),
            current_balance=Decimal("10000.00"),
            realized_pnl=Decimal("0"),
            trades_count=0,
            consecutive_losses=0,
        )

        risk_manager.record_trade_result(Decimal("100.00"))

        assert risk_manager._daily_stats.realized_pnl == Decimal("100.00")
        assert risk_manager._daily_stats.trades_count == 1

    def test_reset_circuit_breaker(self, risk_manager):
        """reset_circuit_breaker should reset consecutive losses to 0."""
        risk_manager._consecutive_losses = 5

        risk_manager.reset_circuit_breaker()

        assert risk_manager._consecutive_losses == 0


class TestRiskManagerStatus:
    """Tests for risk status reporting."""

    @pytest.fixture
    def risk_manager(self):
        """Create a fresh RiskManager instance for each test."""
        return RiskManager()

    def test_get_risk_status_no_daily_stats(self, risk_manager):
        """get_risk_status should handle missing daily stats."""
        with patch("tradingsystem.services.risk_manager.settings") as mock_settings:
            mock_settings.live_trading_enabled = True
            mock_settings.max_position_size_pct = 5.0
            mock_settings.max_daily_loss_pct = 2.0
            mock_settings.max_open_positions = 5

            status = risk_manager.get_risk_status()

            assert status["live_trading_enabled"] is True
            assert status["max_position_size_pct"] == 5.0
            assert status["max_daily_loss_pct"] == 2.0
            assert status["max_open_positions"] == 5
            assert status["consecutive_losses"] == 0
            assert status["circuit_breaker_active"] is False
            assert status["daily_stats"]["date"] is None

    def test_get_risk_status_with_daily_stats(self, risk_manager):
        """get_risk_status should include daily stats when available."""
        with patch("tradingsystem.services.risk_manager.settings") as mock_settings:
            mock_settings.live_trading_enabled = True
            mock_settings.max_position_size_pct = 5.0
            mock_settings.max_daily_loss_pct = 2.0
            mock_settings.max_open_positions = 5

            risk_manager._daily_stats = DailyStats(
                date=date.today(),
                starting_balance=Decimal("10000.00"),
                current_balance=Decimal("10050.00"),
                realized_pnl=Decimal("50.00"),
                trades_count=3,
                consecutive_losses=0,
            )

            status = risk_manager.get_risk_status()

            assert status["daily_stats"]["date"] == str(date.today())
            assert status["daily_stats"]["starting_balance"] == "10000.00"
            assert status["daily_stats"]["realized_pnl"] == "50.00"
            assert status["daily_stats"]["trades_count"] == 3

    def test_get_risk_status_circuit_breaker_active(self, risk_manager):
        """get_risk_status should indicate when circuit breaker is active."""
        with patch("tradingsystem.services.risk_manager.settings") as mock_settings:
            mock_settings.live_trading_enabled = True
            mock_settings.max_position_size_pct = 5.0
            mock_settings.max_daily_loss_pct = 2.0
            mock_settings.max_open_positions = 5

            risk_manager._consecutive_losses = 5
            risk_manager._max_consecutive_losses = 5

            status = risk_manager.get_risk_status()

            assert status["circuit_breaker_active"] is True
            assert status["consecutive_losses"] == 5


class TestRiskManagerDailyReset:
    """Tests for daily stats reset behavior."""

    @pytest.fixture
    def risk_manager(self):
        """Create a fresh RiskManager instance for each test."""
        return RiskManager()

    @pytest.mark.asyncio
    async def test_daily_stats_reset_on_new_day(self, risk_manager, mock_oanda_account):
        """Daily stats should reset when a new day begins."""
        from datetime import timedelta

        yesterday = date.today() - timedelta(days=1)
        risk_manager._daily_stats = DailyStats(
            date=yesterday,
            starting_balance=Decimal("10000.00"),
            current_balance=Decimal("9500.00"),
            realized_pnl=Decimal("-500.00"),
            trades_count=10,
            consecutive_losses=3,
        )
        risk_manager._consecutive_losses = 3

        # Trigger _update_daily_stats via check_trade
        with patch("tradingsystem.services.risk_manager.settings") as mock_settings, \
             patch("tradingsystem.services.risk_manager.oanda_trading_client") as mock_oanda:

            mock_settings.live_trading_enabled = True
            mock_settings.max_position_size_pct = 50.0
            mock_settings.max_daily_loss_pct = 10.0
            mock_settings.max_open_positions = 10

            new_account = mock_oanda_account(balance=Decimal("9500.00"))
            mock_oanda.get_account_summary = AsyncMock(return_value=new_account)
            mock_oanda.get_open_trades = AsyncMock(return_value=[])

            await risk_manager.check_trade(
                instrument="EUR_USD",
                side=OrderSide.BUY,
                quantity=Decimal("100"),
            )

            # Daily stats should be reset for today
            assert risk_manager._daily_stats.date == date.today()
            assert risk_manager._daily_stats.starting_balance == Decimal("9500.00")
            assert risk_manager._daily_stats.realized_pnl == Decimal("0")
            assert risk_manager._daily_stats.trades_count == 0
            assert risk_manager._consecutive_losses == 0
