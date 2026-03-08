"""Unit tests for the Backtest Service."""

import json
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pandas as pd
import pytest

from tradingsystem.models.backtest import (
    BacktestConfig,
    BacktestRequest,
    BacktestResult,
    BacktestSummary,
    BacktestTrade,
    EquityPoint,
    PerformanceMetrics,
)
from tradingsystem.services import backtest_service


@pytest.fixture
def mock_strategy_registry():
    """Mock the StrategyRegistry."""
    with patch("tradingsystem.services.backtest_service.StrategyRegistry") as mock:
        yield mock


@pytest.fixture
def mock_series_service():
    """Mock the series_service."""
    with patch("tradingsystem.services.backtest_service.series_service") as mock:
        yield mock


@pytest.fixture
def sample_dataframe():
    """Create a sample OHLCV DataFrame."""
    return pd.DataFrame({
        "time": pd.date_range(start="2024-01-01", periods=100, freq="1min"),
        "open": [1.0850 + i * 0.0001 for i in range(100)],
        "high": [1.0855 + i * 0.0001 for i in range(100)],
        "low": [1.0845 + i * 0.0001 for i in range(100)],
        "close": [1.0852 + i * 0.0001 for i in range(100)],
        "volume": [1000] * 100,
    })


@pytest.fixture
def sample_backtest_result():
    """Create a sample BacktestResult."""
    now = datetime.now(timezone.utc)
    return BacktestResult(
        id=uuid4(),
        strategy_id="ma_crossover",
        instrument="EUR_USD",
        period="M1",
        start_date=now,
        end_date=now,
        initial_capital=Decimal("10000"),
        final_capital=Decimal("10500"),
        config=BacktestConfig(
            strategy_id="ma_crossover",
            instrument="EUR_USD",
            start_date=now,
            end_date=now,
            initial_capital=Decimal("10000"),
        ),
        metrics=PerformanceMetrics(
            total_return=Decimal("500"),
            total_return_pct=Decimal("5.0"),
            sharpe_ratio=1.5,
            max_drawdown=Decimal("200"),
            max_drawdown_pct=Decimal("2.0"),
            win_rate=60.0,
            profit_factor=1.8,
            avg_win=Decimal("50"),
            avg_loss=Decimal("30"),
            avg_trade=Decimal("25"),
            total_trades=20,
            winning_trades=12,
            losing_trades=8,
        ),
        trades=[
            BacktestTrade(
                entry_time=now,
                exit_time=now,
                side="LONG",
                entry_price=Decimal("1.0850"),
                exit_price=Decimal("1.0900"),
                quantity=Decimal("1000"),
                pnl=Decimal("50"),
                pnl_pct=Decimal("0.46"),
                signal_reason="MA crossover",
            ),
        ],
        equity_curve=[
            EquityPoint(time=now, equity=Decimal("10000")),
            EquityPoint(time=now, equity=Decimal("10500")),
        ],
        created_at=now,
    )


@pytest.fixture
def backtest_request():
    """Create a sample backtest request."""
    now = datetime.now(timezone.utc)
    return BacktestRequest(
        strategy_id="ma_crossover",
        instrument="EUR_USD",
        start_date=now,
        end_date=now,
        initial_capital=Decimal("10000"),
        period="M1",
    )


class TestRunBacktest:
    """Tests for backtest_service.run_backtest()."""

    @pytest.mark.asyncio
    async def test_run_backtest_success(
        self, mock_strategy_registry, mock_series_service, backtest_request, sample_dataframe
    ):
        """run_backtest should execute backtest and return results."""
        from tradingsystem.strategies.base import BaseStrategy, StrategyContext

        class MockStrategy(BaseStrategy):
            name = "ma_crossover"
            instruments = ["EUR_USD"]
            periods = ["M1"]

            def generate_signals(self, context):
                return []

        mock_instance = MockStrategy()
        mock_strategy_registry.get_instance.return_value = mock_instance

        mock_series_service.get_series_dataframe = AsyncMock(return_value=sample_dataframe)

        with patch("tradingsystem.services.backtest_service.BacktestEngine") as mock_engine, \
             patch("tradingsystem.services.backtest_service.save_backtest_result") as mock_save:

            mock_result = MagicMock()
            mock_result.metrics.total_trades = 10
            mock_result.metrics.total_return_pct = 5.0
            mock_result.metrics.win_rate = 60.0
            mock_engine.return_value.run.return_value = mock_result

            mock_save.return_value = mock_result

            result = await backtest_service.run_backtest(backtest_request)

            mock_strategy_registry.get_instance.assert_called_once()
            mock_series_service.get_series_dataframe.assert_called_once()
            mock_engine.return_value.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_backtest_strategy_not_found(
        self, mock_strategy_registry, backtest_request
    ):
        """run_backtest should raise for unknown strategy."""
        mock_strategy_registry.get_instance.return_value = None

        with pytest.raises(ValueError, match="Strategy not found"):
            await backtest_service.run_backtest(backtest_request)

    @pytest.mark.asyncio
    async def test_run_backtest_validation_failed(
        self, mock_strategy_registry, backtest_request
    ):
        """run_backtest should raise if strategy validation fails."""
        from tradingsystem.strategies.base import BaseStrategy

        class InvalidStrategy(BaseStrategy):
            name = ""  # Invalid
            instruments = []
            periods = []

            def generate_signals(self, context):
                return []

        mock_strategy_registry.get_instance.return_value = InvalidStrategy()

        with pytest.raises(ValueError, match="validation failed"):
            await backtest_service.run_backtest(backtest_request)

    @pytest.mark.asyncio
    async def test_run_backtest_no_data(
        self, mock_strategy_registry, mock_series_service, backtest_request
    ):
        """run_backtest should raise when no candle data available."""
        from tradingsystem.strategies.base import BaseStrategy

        class MockStrategy(BaseStrategy):
            name = "test"
            instruments = ["EUR_USD"]
            periods = ["M1"]

            def generate_signals(self, context):
                return []

        mock_strategy_registry.get_instance.return_value = MockStrategy()
        mock_series_service.get_series_dataframe = AsyncMock(return_value=pd.DataFrame())

        with pytest.raises(ValueError, match="No candle data available"):
            await backtest_service.run_backtest(backtest_request)


class TestSaveBacktestResult:
    """Tests for backtest_service.save_backtest_result()."""

    @pytest.mark.asyncio
    async def test_save_backtest_result(self, sample_backtest_result):
        """save_backtest_result should persist result to database."""
        result_id = uuid4()
        created_at = datetime.now(timezone.utc)

        with patch("tradingsystem.services.backtest_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.fetchone = AsyncMock(return_value={
                "id": result_id,
                "started_at": created_at,
            })
            cursor.connection = MagicMock()
            cursor.connection.commit = AsyncMock()

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            result = await backtest_service.save_backtest_result(sample_backtest_result)

            assert result.id == result_id
            assert result.created_at == created_at
            cursor.execute.assert_called_once()


class TestGetBacktest:
    """Tests for backtest_service.get_backtest()."""

    @pytest.mark.asyncio
    async def test_get_backtest_found(self):
        """get_backtest should return result when found."""
        backtest_id = uuid4()
        now = datetime.now(timezone.utc)

        db_row = {
            "id": backtest_id,
            "strategy_id": "ma_crossover",
            "mode": "BACKTEST",
            "started_at": now,
            "ended_at": now,
            "config": {
                "instrument": "EUR_USD",
                "period": "M1",
                "initial_capital": "10000",
            },
            "results": {
                "metrics": {
                    "total_return": "500",
                    "total_return_pct": "5.0",
                    "max_drawdown": "200",
                    "max_drawdown_pct": "2.0",
                    "win_rate": 60.0,
                    "total_trades": 10,
                    "winning_trades": 6,
                    "losing_trades": 4,
                },
                "final_capital": "10500",
                "trades": [],
            },
        }

        with patch("tradingsystem.services.backtest_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.fetchone = AsyncMock(return_value=db_row)

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            result = await backtest_service.get_backtest(backtest_id)

            assert result is not None
            assert result.id == backtest_id
            assert result.strategy_id == "ma_crossover"

    @pytest.mark.asyncio
    async def test_get_backtest_not_found(self):
        """get_backtest should return None when not found."""
        backtest_id = uuid4()

        with patch("tradingsystem.services.backtest_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.fetchone = AsyncMock(return_value=None)

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            result = await backtest_service.get_backtest(backtest_id)

            assert result is None


class TestListBacktests:
    """Tests for backtest_service.list_backtests()."""

    @pytest.mark.asyncio
    async def test_list_backtests(self):
        """list_backtests should return backtest summaries."""
        now = datetime.now(timezone.utc)
        db_rows = [
            {
                "id": uuid4(),
                "strategy_id": "ma_crossover",
                "started_at": now,
                "ended_at": now,
                "config": {"instrument": "EUR_USD"},
                "results": {
                    "metrics": {
                        "total_return_pct": "5.0",
                        "sharpe_ratio": 1.5,
                        "max_drawdown_pct": "2.0",
                        "total_trades": 10,
                        "win_rate": 60.0,
                    },
                },
            },
            {
                "id": uuid4(),
                "strategy_id": "rsi_reversal",
                "started_at": now,
                "ended_at": now,
                "config": {"instrument": "GBP_USD"},
                "results": {
                    "metrics": {
                        "total_return_pct": "3.0",
                        "sharpe_ratio": 1.2,
                        "max_drawdown_pct": "3.5",
                        "total_trades": 15,
                        "win_rate": 55.0,
                    },
                },
            },
        ]

        with patch("tradingsystem.services.backtest_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.fetchall = AsyncMock(return_value=db_rows)

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            result = await backtest_service.list_backtests()

            assert len(result) == 2
            assert result[0].strategy_id == "ma_crossover"
            assert result[1].strategy_id == "rsi_reversal"

    @pytest.mark.asyncio
    async def test_list_backtests_with_filters(self):
        """list_backtests should apply filters."""
        now = datetime.now(timezone.utc)
        db_rows = [
            {
                "id": uuid4(),
                "strategy_id": "ma_crossover",
                "started_at": now,
                "ended_at": now,
                "config": {"instrument": "EUR_USD"},
                "results": {"metrics": {"total_return_pct": "5.0", "max_drawdown_pct": "2.0", "total_trades": 10, "win_rate": 60.0}},
            },
        ]

        with patch("tradingsystem.services.backtest_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            executed_queries = []

            async def capture_execute(query, params=None):
                executed_queries.append((query, params))

            cursor.execute = AsyncMock(side_effect=capture_execute)
            cursor.fetchall = AsyncMock(return_value=db_rows)

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            await backtest_service.list_backtests(
                strategy_id="ma_crossover",
                instrument="EUR_USD",
            )

            # Verify filters were applied
            query = executed_queries[0][0]
            assert "strategy_id = %s" in query
            assert "instrument" in query

    @pytest.mark.asyncio
    async def test_list_backtests_empty(self):
        """list_backtests should return empty list when none found."""
        with patch("tradingsystem.services.backtest_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.fetchall = AsyncMock(return_value=[])

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            result = await backtest_service.list_backtests()

            assert result == []


class TestDeleteBacktest:
    """Tests for backtest_service.delete_backtest()."""

    @pytest.mark.asyncio
    async def test_delete_backtest_success(self):
        """delete_backtest should return True when deleted."""
        backtest_id = uuid4()

        with patch("tradingsystem.services.backtest_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.rowcount = 1
            cursor.connection = MagicMock()
            cursor.connection.commit = AsyncMock()

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            result = await backtest_service.delete_backtest(backtest_id)

            assert result is True

    @pytest.mark.asyncio
    async def test_delete_backtest_not_found(self):
        """delete_backtest should return False when not found."""
        backtest_id = uuid4()

        with patch("tradingsystem.services.backtest_service.get_cursor") as mock_cursor_ctx:
            cursor = MagicMock()
            cursor.execute = AsyncMock()
            cursor.rowcount = 0
            cursor.connection = MagicMock()
            cursor.connection.commit = AsyncMock()

            mock_cursor_ctx.return_value.__aenter__ = AsyncMock(return_value=cursor)
            mock_cursor_ctx.return_value.__aexit__ = AsyncMock()

            result = await backtest_service.delete_backtest(backtest_id)

            assert result is False


class TestRowToBacktestResult:
    """Tests for backtest_service._row_to_backtest_result()."""

    def test_row_to_backtest_result(self):
        """Should convert database row to BacktestResult."""
        now = datetime.now(timezone.utc)
        row = {
            "id": uuid4(),
            "strategy_id": "ma_crossover",
            "mode": "BACKTEST",
            "started_at": now,
            "ended_at": now,
            "config": {
                "instrument": "EUR_USD",
                "period": "M1",
                "initial_capital": "10000",
            },
            "results": {
                "metrics": {
                    "total_return": "500",
                    "total_return_pct": "5.0",
                    "max_drawdown": "200",
                    "max_drawdown_pct": "2.0",
                    "win_rate": 60.0,
                    "total_trades": 10,
                    "winning_trades": 6,
                    "losing_trades": 4,
                },
                "final_capital": "10500",
                "trades": [
                    {
                        "entry_time": now.isoformat(),
                        "exit_time": now.isoformat(),
                        "side": "LONG",
                        "entry_price": "1.0850",
                        "exit_price": "1.0900",
                        "quantity": "1000",
                        "pnl": "50",
                        "pnl_pct": "0.46",
                        "signal_reason": "Test",
                    }
                ],
            },
        }

        result = backtest_service._row_to_backtest_result(row)

        assert result.strategy_id == "ma_crossover"
        assert result.instrument == "EUR_USD"
        assert result.metrics.total_trades == 10
        assert result.metrics.win_rate == 60.0
        assert len(result.trades) == 1
        assert result.trades[0].side == "LONG"

    def test_row_to_backtest_result_empty_data(self):
        """Should handle missing optional fields."""
        now = datetime.now(timezone.utc)
        row = {
            "id": uuid4(),
            "strategy_id": "test",
            "mode": "BACKTEST",
            "started_at": now,
            "ended_at": now,
            "config": None,
            "results": None,
        }

        result = backtest_service._row_to_backtest_result(row)

        assert result.strategy_id == "test"
        assert result.instrument == "unknown"
        assert result.trades == []
