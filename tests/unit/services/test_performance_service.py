"""Unit tests for the Performance Service."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from tradingsystem.services import performance_service


@pytest.fixture
def mock_oanda_client():
    """Mock the OANDA trading client."""
    with patch("tradingsystem.services.performance_service.oanda_trading_client") as mock:
        yield mock


@pytest.fixture
def mock_oanda_account(mock_oanda_account):
    """Create a mock OANDA account factory."""
    return mock_oanda_account


class TestGetPortfolioSnapshot:
    """Tests for performance_service.get_portfolio_snapshot()."""

    @pytest.mark.asyncio
    async def test_portfolio_snapshot_with_oanda(self, mock_oanda_client, mock_oanda_account):
        """Should return portfolio snapshot with OANDA data."""
        account = mock_oanda_account(
            balance=Decimal("10000.00"),
            nav=Decimal("10050.00"),
            unrealized_pnl=Decimal("50.00"),
            margin_used=Decimal("500.00"),
            margin_available=Decimal("9500.00"),
        )
        mock_oanda_client.get_account_summary = AsyncMock(return_value=account)

        with patch("tradingsystem.services.performance_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            # Sequence of fetchone results: open_positions, realized_pnl, daily_pnl, weekly_pnl
            cursor.fetchone = AsyncMock(side_effect=[
                {"count": 3},
                {"total": Decimal("500.00")},
                {"total": Decimal("50.00")},
                {"total": Decimal("150.00")},
            ])
            cursor.execute = AsyncMock()

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            snapshot = await performance_service.get_portfolio_snapshot()

            assert snapshot.account_balance == Decimal("10000.00")
            assert snapshot.nav == Decimal("10050.00")
            assert snapshot.unrealized_pnl == Decimal("50.00")
            assert snapshot.realized_pnl == Decimal("500.00")
            assert snapshot.open_positions == 3
            assert snapshot.daily_pnl == Decimal("50.00")
            assert snapshot.weekly_pnl == Decimal("150.00")

    @pytest.mark.asyncio
    async def test_portfolio_snapshot_oanda_failure(self, mock_oanda_client):
        """Should handle OANDA failure gracefully."""
        mock_oanda_client.get_account_summary = AsyncMock(
            side_effect=Exception("OANDA error")
        )

        with patch("tradingsystem.services.performance_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            cursor.fetchone = AsyncMock(side_effect=[
                {"count": 0},
                {"total": Decimal("0")},
                {"total": Decimal("0")},
                {"total": Decimal("0")},
            ])
            cursor.execute = AsyncMock()

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            snapshot = await performance_service.get_portfolio_snapshot()

            # Should use zeros for OANDA data
            assert snapshot.account_balance == Decimal("0")
            assert snapshot.nav == Decimal("0")


class TestGetPerformanceMetrics:
    """Tests for performance_service.get_performance_metrics()."""

    @pytest.mark.asyncio
    async def test_performance_metrics_all_time(self):
        """Should calculate all-time performance metrics."""
        db_rows = [
            {"pnl": Decimal("50.00"), "entry_price": Decimal("1.0850"), "quantity": Decimal("1000")},
            {"pnl": Decimal("30.00"), "entry_price": Decimal("1.0850"), "quantity": Decimal("1000")},
            {"pnl": Decimal("-20.00"), "entry_price": Decimal("1.0850"), "quantity": Decimal("1000")},
            {"pnl": Decimal("-10.00"), "entry_price": Decimal("1.0850"), "quantity": Decimal("1000")},
        ]

        with patch("tradingsystem.services.performance_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.fetchall = AsyncMock(return_value=db_rows)

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            metrics = await performance_service.get_performance_metrics(period="all_time")

            assert metrics.total_trades == 4
            assert metrics.winning_trades == 2
            assert metrics.losing_trades == 2
            assert metrics.win_rate == 0.5
            assert metrics.total_pnl == Decimal("50.00")
            assert metrics.gross_profit == Decimal("80.00")  # 50 + 30
            assert metrics.gross_loss == Decimal("30.00")  # abs(-20 + -10)
            assert metrics.largest_win == Decimal("50.00")
            assert metrics.largest_loss == Decimal("20.00")

    @pytest.mark.asyncio
    async def test_performance_metrics_daily(self):
        """Should filter by daily period."""
        db_rows = [
            {"pnl": Decimal("25.00"), "entry_price": Decimal("1.0850"), "quantity": Decimal("1000")},
        ]

        with patch("tradingsystem.services.performance_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            executed_queries = []

            async def capture_execute(query, params=None):
                executed_queries.append((query, params))

            cursor.execute = AsyncMock(side_effect=capture_execute)
            cursor.fetchall = AsyncMock(return_value=db_rows)

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            metrics = await performance_service.get_performance_metrics(period="daily")

            assert metrics.period == "daily"
            # Verify time filter was applied
            params = executed_queries[0][1]
            assert params[1].date() == datetime.now(timezone.utc).date()

    @pytest.mark.asyncio
    async def test_performance_metrics_no_trades(self):
        """Should handle periods with no trades."""
        with patch("tradingsystem.services.performance_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.fetchall = AsyncMock(return_value=[])

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            metrics = await performance_service.get_performance_metrics(period="daily")

            assert metrics.total_trades == 0
            assert metrics.win_rate == 0.0
            assert metrics.total_pnl == Decimal("0")
            assert metrics.profit_factor is None

    @pytest.mark.asyncio
    async def test_performance_metrics_all_wins(self):
        """Should handle all winning trades."""
        db_rows = [
            {"pnl": Decimal("50.00"), "entry_price": Decimal("1.0850"), "quantity": Decimal("1000")},
            {"pnl": Decimal("30.00"), "entry_price": Decimal("1.0850"), "quantity": Decimal("1000")},
        ]

        with patch("tradingsystem.services.performance_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.fetchall = AsyncMock(return_value=db_rows)

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            metrics = await performance_service.get_performance_metrics()

            assert metrics.win_rate == 1.0
            assert metrics.gross_loss == Decimal("0")
            assert metrics.profit_factor is None  # Can't divide by zero loss


class TestGetStrategyPerformance:
    """Tests for performance_service.get_strategy_performance()."""

    @pytest.mark.asyncio
    async def test_strategy_performance(self):
        """Should calculate strategy-specific metrics."""
        db_row = {
            "total_trades": 20,
            "winning_trades": 12,
            "total_pnl": Decimal("500.00"),
            "average_pnl": Decimal("25.00"),
            "max_loss": Decimal("-100.00"),
        }

        with patch("tradingsystem.services.performance_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.fetchone = AsyncMock(return_value=db_row)

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            perf = await performance_service.get_strategy_performance("ma_crossover")

            assert perf.strategy_id == "ma_crossover"
            assert perf.total_trades == 20
            assert perf.winning_trades == 12
            assert perf.win_rate == 0.6
            assert perf.total_pnl == Decimal("500.00")
            assert perf.max_drawdown == Decimal("100.00")

    @pytest.mark.asyncio
    async def test_strategy_performance_no_trades(self):
        """Should handle strategy with no trades."""
        db_row = {
            "total_trades": 0,
            "winning_trades": 0,
            "total_pnl": Decimal("0"),
            "average_pnl": Decimal("0"),
            "max_loss": Decimal("0"),
        }

        with patch("tradingsystem.services.performance_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.fetchone = AsyncMock(return_value=db_row)

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            perf = await performance_service.get_strategy_performance("unused_strategy")

            assert perf.total_trades == 0
            assert perf.win_rate == 0.0


class TestGetAllStrategyPerformance:
    """Tests for performance_service.get_all_strategy_performance()."""

    @pytest.mark.asyncio
    async def test_all_strategy_performance(self):
        """Should return performance for all strategies."""
        strategy_rows = [
            {"strategy_id": "ma_crossover"},
            {"strategy_id": "rsi_reversal"},
        ]

        perf_row = {
            "total_trades": 10,
            "winning_trades": 6,
            "total_pnl": Decimal("100.00"),
            "average_pnl": Decimal("10.00"),
            "max_loss": Decimal("-50.00"),
        }

        with patch("tradingsystem.services.performance_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            cursor.execute = AsyncMock()
            # First call: list strategies, then two calls for each strategy
            cursor.fetchall = AsyncMock(return_value=strategy_rows)
            cursor.fetchone = AsyncMock(return_value=perf_row)

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            results = await performance_service.get_all_strategy_performance()

            assert len(results) == 2

    @pytest.mark.asyncio
    async def test_all_strategy_performance_empty(self):
        """Should return empty list when no strategies have trades."""
        with patch("tradingsystem.services.performance_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.fetchall = AsyncMock(return_value=[])

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            results = await performance_service.get_all_strategy_performance()

            assert results == []


class TestGetTradeHistory:
    """Tests for performance_service.get_trade_history()."""

    @pytest.mark.asyncio
    async def test_trade_history(self):
        """Should return trade history records."""
        now = datetime.now(timezone.utc)
        db_rows = [
            {
                "id": uuid4(),
                "instrument": "EUR_USD",
                "side": "LONG",
                "quantity": Decimal("1000"),
                "entry_price": Decimal("1.0850"),
                "exit_price": Decimal("1.0900"),
                "entry_time": now,
                "exit_time": now,
                "pnl": Decimal("50.00"),
                "pnl_percent": Decimal("0.46"),
                "strategy_id": "ma_crossover",
            },
        ]

        with patch("tradingsystem.services.performance_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.fetchall = AsyncMock(return_value=db_rows)

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            history = await performance_service.get_trade_history(limit=50)

            assert len(history) == 1
            assert history[0]["instrument"] == "EUR_USD"
            assert history[0]["pnl"] == "50.00"

    @pytest.mark.asyncio
    async def test_trade_history_with_strategy_filter(self):
        """Should filter by strategy."""
        now = datetime.now(timezone.utc)
        db_rows = [
            {
                "id": uuid4(),
                "instrument": "EUR_USD",
                "side": "LONG",
                "quantity": Decimal("1000"),
                "entry_price": Decimal("1.0850"),
                "exit_price": Decimal("1.0900"),
                "entry_time": now,
                "exit_time": now,
                "pnl": Decimal("50.00"),
                "pnl_percent": Decimal("0.46"),
                "strategy_id": "ma_crossover",
            },
        ]

        with patch("tradingsystem.services.performance_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            executed_queries = []

            async def capture_execute(query, params=None):
                executed_queries.append((query, params))

            cursor.execute = AsyncMock(side_effect=capture_execute)
            cursor.fetchall = AsyncMock(return_value=db_rows)

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            await performance_service.get_trade_history(strategy_id="ma_crossover")

            # Verify filter was applied
            query = executed_queries[0][0]
            assert "strategy_id = %s" in query


class TestGetEquityCurve:
    """Tests for performance_service.get_equity_curve()."""

    @pytest.mark.asyncio
    async def test_equity_curve(self):
        """Should return cumulative equity curve."""
        from datetime import date

        db_rows = [
            {"date": date(2024, 1, 1), "daily_pnl": Decimal("100.00")},
            {"date": date(2024, 1, 2), "daily_pnl": Decimal("-30.00")},
            {"date": date(2024, 1, 3), "daily_pnl": Decimal("50.00")},
        ]

        with patch("tradingsystem.services.performance_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.fetchall = AsyncMock(return_value=db_rows)

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            curve = await performance_service.get_equity_curve(days=30)

            assert len(curve) == 3
            assert curve[0]["cumulative_pnl"] == "100.00"
            assert curve[1]["cumulative_pnl"] == "70.00"  # 100 - 30
            assert curve[2]["cumulative_pnl"] == "120.00"  # 70 + 50

    @pytest.mark.asyncio
    async def test_equity_curve_empty(self):
        """Should handle empty equity curve."""
        with patch("tradingsystem.services.performance_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.fetchall = AsyncMock(return_value=[])

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            curve = await performance_service.get_equity_curve()

            assert curve == []
