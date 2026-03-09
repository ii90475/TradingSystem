"""Tests for signal processor — strategy execution on bar close."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pandas as pd
import pytest

from tradingsystem.services.bar_close_service import BarCloseEvent
from tradingsystem.services.signal_processor import (
    handle_bar_close,
    _evaluate_strategy,
    _get_enabled_chart_strategies,
)


def _make_event(instrument="EUR_USD", period="H1"):
    return BarCloseEvent(
        instrument=instrument,
        period=period,
        bar_time=datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc),
    )


def _make_df():
    """Create a minimal candle DataFrame."""
    data = {
        "open": [1.0800, 1.0810, 1.0820],
        "high": [1.0830, 1.0840, 1.0850],
        "low": [1.0790, 1.0800, 1.0810],
        "close": [1.0810, 1.0820, 1.0830],
        "volume": [100, 150, 120],
    }
    index = pd.to_datetime([
        "2026-03-09T10:00:00Z",
        "2026-03-09T11:00:00Z",
        "2026-03-09T12:00:00Z",
    ])
    return pd.DataFrame(data, index=index)


def _make_chart_strategy(strategy_id="ma_crossover", params=None):
    return {
        "id": uuid4(),
        "chart_id": uuid4(),
        "strategy_id": strategy_id,
        "name": "Test Strategy",
        "parameters": params or {},
    }


# --- handle_bar_close Tests ---


class TestHandleBarClose:
    """Tests for the main bar close handler."""

    @pytest.mark.asyncio
    async def test_no_enabled_strategies(self):
        """When no strategies are enabled, return zero evaluated."""
        with patch(
            "tradingsystem.services.signal_processor._get_enabled_chart_strategies",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await handle_bar_close(_make_event())

        assert result["strategies_evaluated"] == 0

    @pytest.mark.asyncio
    async def test_no_candle_data(self):
        """When candle data is empty, return error."""
        with (
            patch(
                "tradingsystem.services.signal_processor._get_enabled_chart_strategies",
                new_callable=AsyncMock,
                return_value=[_make_chart_strategy()],
            ),
            patch(
                "tradingsystem.services.signal_processor.series_service"
            ) as mock_ss,
        ):
            mock_ss.get_series_dataframe = AsyncMock(
                return_value=pd.DataFrame()
            )
            result = await handle_bar_close(_make_event())

        assert result["error"] == "no_candle_data"

    @pytest.mark.asyncio
    async def test_evaluates_all_strategies(self):
        """Should evaluate each enabled strategy independently."""
        cs1 = _make_chart_strategy("ma_crossover")
        cs2 = _make_chart_strategy("rsi_reversal")

        with (
            patch(
                "tradingsystem.services.signal_processor._get_enabled_chart_strategies",
                new_callable=AsyncMock,
                return_value=[cs1, cs2],
            ),
            patch(
                "tradingsystem.services.signal_processor.series_service"
            ) as mock_ss,
            patch(
                "tradingsystem.services.signal_processor._evaluate_strategy",
                new_callable=AsyncMock,
                return_value={"signals": 1, "status": "ok"},
            ) as mock_eval,
        ):
            mock_ss.get_series_dataframe = AsyncMock(return_value=_make_df())
            result = await handle_bar_close(_make_event())

        assert result["strategies_evaluated"] == 2
        assert result["total_signals"] == 2
        assert mock_eval.await_count == 2

    @pytest.mark.asyncio
    async def test_returns_per_strategy_results(self):
        """Result should include per-strategy outcome details."""
        cs = _make_chart_strategy()

        with (
            patch(
                "tradingsystem.services.signal_processor._get_enabled_chart_strategies",
                new_callable=AsyncMock,
                return_value=[cs],
            ),
            patch(
                "tradingsystem.services.signal_processor.series_service"
            ) as mock_ss,
            patch(
                "tradingsystem.services.signal_processor._evaluate_strategy",
                new_callable=AsyncMock,
                return_value={
                    "chart_strategy_id": str(cs["id"]),
                    "strategy_id": "ma_crossover",
                    "status": "ok",
                    "signals": 2,
                    "elapsed_ms": 15.3,
                },
            ),
        ):
            mock_ss.get_series_dataframe = AsyncMock(return_value=_make_df())
            result = await handle_bar_close(_make_event())

        assert len(result["results"]) == 1
        assert result["results"][0]["status"] == "ok"


# --- _evaluate_strategy Tests ---


class TestEvaluateStrategy:
    """Tests for individual strategy evaluation."""

    @pytest.mark.asyncio
    async def test_strategy_not_in_registry(self):
        """Unknown strategy_id returns error status."""
        cs = _make_chart_strategy("nonexistent_strategy")

        with patch(
            "tradingsystem.services.signal_processor.StrategyRegistry"
        ) as mock_reg:
            mock_reg.get_instance.return_value = None
            result = await _evaluate_strategy(
                cs=cs,
                instrument="EUR_USD",
                period="H1",
                df=_make_df(),
                current_price=1.0830,
            )

        assert result["status"] == "error"
        assert result["error"] == "strategy_not_found"

    @pytest.mark.asyncio
    async def test_successful_evaluation_no_signals(self):
        """Strategy runs but generates no signals."""
        cs = _make_chart_strategy()
        mock_instance = MagicMock()
        mock_instance.generate_signals.return_value = []
        mock_instance.required_indicators = []

        with (
            patch(
                "tradingsystem.services.signal_processor.StrategyRegistry"
            ) as mock_reg,
            patch(
                "tradingsystem.services.strategy_service._calculate_strategy_indicators",
                new_callable=AsyncMock,
                return_value={},
            ),
            patch(
                "tradingsystem.services.signal_processor.signal_service"
            ) as mock_sig,
        ):
            mock_reg.get_instance.return_value = mock_instance
            result = await _evaluate_strategy(
                cs=cs,
                instrument="EUR_USD",
                period="H1",
                df=_make_df(),
                current_price=1.0830,
            )

        assert result["status"] == "ok"
        assert result["signals"] == 0
        mock_sig.save_signals.assert_not_called()

    @pytest.mark.asyncio
    async def test_successful_evaluation_with_signals(self):
        """Strategy generates signals, which get saved."""
        cs = _make_chart_strategy()
        mock_signal = MagicMock()
        mock_instance = MagicMock()
        mock_instance.generate_signals.return_value = [mock_signal]
        mock_instance.required_indicators = []

        with (
            patch(
                "tradingsystem.services.signal_processor.StrategyRegistry"
            ) as mock_reg,
            patch(
                "tradingsystem.services.strategy_service._calculate_strategy_indicators",
                new_callable=AsyncMock,
                return_value={},
            ),
            patch(
                "tradingsystem.services.signal_processor.signal_service"
            ) as mock_sig,
        ):
            mock_reg.get_instance.return_value = mock_instance
            mock_sig.save_signals = AsyncMock()
            result = await _evaluate_strategy(
                cs=cs,
                instrument="EUR_USD",
                period="H1",
                df=_make_df(),
                current_price=1.0830,
            )

        assert result["status"] == "ok"
        assert result["signals"] == 1
        mock_sig.save_signals.assert_awaited_once_with([mock_signal])

    @pytest.mark.asyncio
    async def test_strategy_exception_returns_error(self):
        """Strategy that throws is caught and reported, not raised."""
        cs = _make_chart_strategy()
        mock_instance = MagicMock()
        mock_instance.generate_signals.side_effect = RuntimeError("indicator crash")
        mock_instance.required_indicators = []

        with (
            patch(
                "tradingsystem.services.signal_processor.StrategyRegistry"
            ) as mock_reg,
            patch(
                "tradingsystem.services.strategy_service._calculate_strategy_indicators",
                new_callable=AsyncMock,
                return_value={},
            ),
        ):
            mock_reg.get_instance.return_value = mock_instance
            result = await _evaluate_strategy(
                cs=cs,
                instrument="EUR_USD",
                period="H1",
                df=_make_df(),
                current_price=1.0830,
            )

        assert result["status"] == "error"
        assert "indicator crash" in result["error"]
        assert "elapsed_ms" in result

    @pytest.mark.asyncio
    async def test_elapsed_time_recorded(self):
        """Result includes elapsed_ms for performance tracking."""
        cs = _make_chart_strategy()
        mock_instance = MagicMock()
        mock_instance.generate_signals.return_value = []
        mock_instance.required_indicators = []

        with (
            patch(
                "tradingsystem.services.signal_processor.StrategyRegistry"
            ) as mock_reg,
            patch(
                "tradingsystem.services.strategy_service._calculate_strategy_indicators",
                new_callable=AsyncMock,
                return_value={},
            ),
        ):
            mock_reg.get_instance.return_value = mock_instance
            result = await _evaluate_strategy(
                cs=cs,
                instrument="EUR_USD",
                period="H1",
                df=_make_df(),
                current_price=1.0830,
            )

        assert isinstance(result["elapsed_ms"], float)

    @pytest.mark.asyncio
    async def test_strategy_params_passed_to_instance(self):
        """Chart strategy parameters are forwarded to StrategyRegistry.get_instance."""
        params = {"fast_period": 5, "slow_period": 20}
        cs = _make_chart_strategy(params=params)
        mock_instance = MagicMock()
        mock_instance.generate_signals.return_value = []
        mock_instance.required_indicators = []

        with (
            patch(
                "tradingsystem.services.signal_processor.StrategyRegistry"
            ) as mock_reg,
            patch(
                "tradingsystem.services.strategy_service._calculate_strategy_indicators",
                new_callable=AsyncMock,
                return_value={},
            ),
        ):
            mock_reg.get_instance.return_value = mock_instance
            await _evaluate_strategy(
                cs=cs,
                instrument="EUR_USD",
                period="H1",
                df=_make_df(),
                current_price=1.0830,
            )

        mock_reg.get_instance.assert_called_once_with(
            "ma_crossover", fast_period=5, slow_period=20
        )


# --- _get_enabled_chart_strategies Tests ---


class TestGetEnabledChartStrategies:
    """Tests for the DB query that finds enabled strategies."""

    @pytest.mark.asyncio
    async def test_returns_enabled_strategies(self):
        mock_cursor = AsyncMock()
        mock_cursor.fetchall = AsyncMock(
            return_value=[
                {
                    "id": uuid4(),
                    "chart_id": uuid4(),
                    "strategy_id": "ma_crossover",
                    "name": "Fast MA",
                    "parameters": {"fast": 10},
                },
            ]
        )
        mock_cursor.connection = MagicMock()

        with patch(
            "tradingsystem.services.signal_processor.get_cursor"
        ) as mock_gc:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_gc.return_value = mock_ctx

            result = await _get_enabled_chart_strategies("EUR_USD", "H1")

        assert len(result) == 1
        assert result[0]["strategy_id"] == "ma_crossover"

    @pytest.mark.asyncio
    async def test_returns_empty_when_none_enabled(self):
        mock_cursor = AsyncMock()
        mock_cursor.fetchall = AsyncMock(return_value=[])
        mock_cursor.connection = MagicMock()

        with patch(
            "tradingsystem.services.signal_processor.get_cursor"
        ) as mock_gc:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_gc.return_value = mock_ctx

            result = await _get_enabled_chart_strategies("EUR_USD", "H1")

        assert result == []
