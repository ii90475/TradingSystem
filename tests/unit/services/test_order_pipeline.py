"""Tests for signal-to-order pipeline."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from tradingsystem.models.signal import Signal, SignalType
from tradingsystem.services.live_trading_service import LiveTradingError
from tradingsystem.services.order_pipeline import (
    DEFAULT_MIN_SIGNAL_STRENGTH,
    DEFAULT_ORDER_UNITS,
    OrderResult,
    process_signals,
    _process_single_signal,
)


def _make_signal(
    signal_type=SignalType.BUY,
    strength=Decimal("0.8"),
    instrument="EUR_USD",
    strategy_id="ma_crossover",
    reason="Test signal",
):
    return Signal(
        id=uuid4(),
        time=datetime.now(timezone.utc),
        strategy_id=strategy_id,
        instrument=instrument,
        signal_type=signal_type,
        strength=strength,
        reason=reason,
    )


# --- OrderResult Tests ---


class TestOrderResult:
    def test_creation(self):
        signal = _make_signal()
        result = OrderResult(signal=signal, action="order_placed", reason="test")
        assert result.action == "order_placed"
        assert result.order_id is None
        assert result.details == {}


# --- Signal Filtering Tests ---


class TestSignalFiltering:
    @pytest.mark.asyncio
    async def test_hold_signal_skipped(self):
        signal = _make_signal(signal_type=SignalType.HOLD)
        result = await _process_single_signal(
            signal, DEFAULT_ORDER_UNITS, DEFAULT_MIN_SIGNAL_STRENGTH, True
        )
        assert result.action == "skipped"
        assert "HOLD" in result.reason

    @pytest.mark.asyncio
    async def test_weak_signal_skipped(self):
        signal = _make_signal(strength=Decimal("0.2"))
        result = await _process_single_signal(
            signal, DEFAULT_ORDER_UNITS, Decimal("0.5"), True
        )
        assert result.action == "skipped"
        assert "below threshold" in result.reason

    @pytest.mark.asyncio
    async def test_signal_at_threshold_passes(self):
        """Signal exactly at threshold should not be skipped for strength."""
        signal = _make_signal(strength=Decimal("0.5"))

        with patch(
            "tradingsystem.services.order_pipeline.execute_live_trade",
            new_callable=AsyncMock,
        ) as mock_exec:
            mock_order = MagicMock()
            mock_order.id = uuid4()
            mock_position = MagicMock()
            mock_position.id = uuid4()
            mock_response = MagicMock()
            mock_response.price = Decimal("1.0820")
            mock_response.order_id = "oanda-123"
            mock_exec.return_value = (mock_order, mock_position, mock_response)

            with patch(
                "tradingsystem.services.order_pipeline.oanda_trading_client"
            ) as mock_client:
                mock_client.trading_mode = "PAPER"
                result = await _process_single_signal(
                    signal, DEFAULT_ORDER_UNITS, Decimal("0.5"), True
                )

        assert result.action == "order_placed"

    @pytest.mark.asyncio
    async def test_dry_run_mode(self):
        signal = _make_signal()

        with patch(
            "tradingsystem.services.order_pipeline.oanda_trading_client"
        ) as mock_client:
            mock_client.trading_mode = "PAPER"
            result = await _process_single_signal(
                signal, DEFAULT_ORDER_UNITS, DEFAULT_MIN_SIGNAL_STRENGTH, False
            )

        assert result.action == "skipped"
        assert "dry-run" in result.reason
        assert result.details["would_place"] is True


# --- Order Execution Tests ---


class TestOrderExecution:
    @pytest.mark.asyncio
    async def test_buy_signal_places_buy_order(self):
        signal = _make_signal(signal_type=SignalType.BUY)

        with (
            patch(
                "tradingsystem.services.order_pipeline.execute_live_trade",
                new_callable=AsyncMock,
            ) as mock_exec,
            patch(
                "tradingsystem.services.order_pipeline.oanda_trading_client"
            ) as mock_client,
        ):
            mock_client.trading_mode = "PAPER"
            mock_order = MagicMock()
            mock_order.id = uuid4()
            mock_position = MagicMock()
            mock_position.id = uuid4()
            mock_response = MagicMock()
            mock_response.price = Decimal("1.0820")
            mock_response.order_id = "oanda-123"
            mock_exec.return_value = (mock_order, mock_position, mock_response)

            result = await _process_single_signal(
                signal, Decimal("5000"), DEFAULT_MIN_SIGNAL_STRENGTH, True
            )

        assert result.action == "order_placed"
        assert result.trading_mode == "PAPER"
        mock_exec.assert_awaited_once()
        call_kwargs = mock_exec.call_args
        assert call_kwargs[1]["side"].value == "BUY"
        assert call_kwargs[1]["quantity"] == Decimal("5000")

    @pytest.mark.asyncio
    async def test_sell_signal_places_sell_order(self):
        signal = _make_signal(signal_type=SignalType.SELL)

        with (
            patch(
                "tradingsystem.services.order_pipeline.execute_live_trade",
                new_callable=AsyncMock,
            ) as mock_exec,
            patch(
                "tradingsystem.services.order_pipeline.oanda_trading_client"
            ) as mock_client,
        ):
            mock_client.trading_mode = "LIVE"
            mock_order = MagicMock()
            mock_order.id = uuid4()
            mock_position = MagicMock()
            mock_position.id = uuid4()
            mock_response = MagicMock()
            mock_response.price = Decimal("1.0820")
            mock_response.order_id = "oanda-456"
            mock_exec.return_value = (mock_order, mock_position, mock_response)

            result = await _process_single_signal(
                signal, DEFAULT_ORDER_UNITS, DEFAULT_MIN_SIGNAL_STRENGTH, True
            )

        assert result.action == "order_placed"
        assert result.trading_mode == "LIVE"
        call_kwargs = mock_exec.call_args
        assert call_kwargs[1]["side"].value == "SELL"

    @pytest.mark.asyncio
    async def test_order_result_includes_details(self):
        signal = _make_signal(reason="EMA crossover detected")

        with (
            patch(
                "tradingsystem.services.order_pipeline.execute_live_trade",
                new_callable=AsyncMock,
            ) as mock_exec,
            patch(
                "tradingsystem.services.order_pipeline.oanda_trading_client"
            ) as mock_client,
        ):
            mock_client.trading_mode = "PAPER"
            mock_order = MagicMock()
            mock_order.id = uuid4()
            mock_position = MagicMock()
            mock_position.id = uuid4()
            mock_response = MagicMock()
            mock_response.price = Decimal("1.0830")
            mock_response.order_id = "oanda-789"
            mock_exec.return_value = (mock_order, mock_position, mock_response)

            result = await _process_single_signal(
                signal, DEFAULT_ORDER_UNITS, DEFAULT_MIN_SIGNAL_STRENGTH, True
            )

        assert result.details["fill_price"] == "1.0830"
        assert result.details["signal_reason"] == "EMA crossover detected"
        assert result.details["signal_strength"] == "0.8"


# --- Risk Rejection Tests ---


class TestRiskRejection:
    @pytest.mark.asyncio
    async def test_risk_rejection_returns_rejected(self):
        signal = _make_signal()

        with (
            patch(
                "tradingsystem.services.order_pipeline.execute_live_trade",
                new_callable=AsyncMock,
                side_effect=LiveTradingError(
                    "Trade rejected by risk manager: Max open positions"
                ),
            ),
            patch(
                "tradingsystem.services.order_pipeline.oanda_trading_client"
            ) as mock_client,
        ):
            mock_client.trading_mode = "PAPER"
            result = await _process_single_signal(
                signal, DEFAULT_ORDER_UNITS, DEFAULT_MIN_SIGNAL_STRENGTH, True
            )

        assert result.action == "rejected"
        assert "risk manager" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_execution_failure_returns_error(self):
        signal = _make_signal()

        with (
            patch(
                "tradingsystem.services.order_pipeline.execute_live_trade",
                new_callable=AsyncMock,
                side_effect=LiveTradingError("Oanda execution failed: timeout"),
            ),
            patch(
                "tradingsystem.services.order_pipeline.oanda_trading_client"
            ) as mock_client,
        ):
            mock_client.trading_mode = "PAPER"
            result = await _process_single_signal(
                signal, DEFAULT_ORDER_UNITS, DEFAULT_MIN_SIGNAL_STRENGTH, True
            )

        assert result.action == "error"

    @pytest.mark.asyncio
    async def test_unexpected_error_returns_error(self):
        signal = _make_signal()

        with (
            patch(
                "tradingsystem.services.order_pipeline.execute_live_trade",
                new_callable=AsyncMock,
                side_effect=RuntimeError("unexpected"),
            ),
            patch(
                "tradingsystem.services.order_pipeline.oanda_trading_client"
            ) as mock_client,
        ):
            mock_client.trading_mode = "PAPER"
            result = await _process_single_signal(
                signal, DEFAULT_ORDER_UNITS, DEFAULT_MIN_SIGNAL_STRENGTH, True
            )

        assert result.action == "error"
        assert "unexpected" in result.reason


# --- Batch Processing Tests ---


class TestProcessSignals:
    @pytest.mark.asyncio
    async def test_empty_signals_list(self):
        results = await process_signals([])
        assert results == []

    @pytest.mark.asyncio
    async def test_multiple_signals_processed_independently(self):
        buy = _make_signal(signal_type=SignalType.BUY, strength=Decimal("0.9"))
        hold = _make_signal(signal_type=SignalType.HOLD)
        weak = _make_signal(signal_type=SignalType.SELL, strength=Decimal("0.1"))

        with (
            patch(
                "tradingsystem.services.order_pipeline.execute_live_trade",
                new_callable=AsyncMock,
            ) as mock_exec,
            patch(
                "tradingsystem.services.order_pipeline.oanda_trading_client"
            ) as mock_client,
        ):
            mock_client.trading_mode = "PAPER"
            mock_order = MagicMock()
            mock_order.id = uuid4()
            mock_position = MagicMock()
            mock_position.id = uuid4()
            mock_response = MagicMock()
            mock_response.price = Decimal("1.0820")
            mock_response.order_id = "oanda-001"
            mock_exec.return_value = (mock_order, mock_position, mock_response)

            results = await process_signals([buy, hold, weak])

        assert len(results) == 3
        assert results[0].action == "order_placed"  # BUY with strength 0.9
        assert results[1].action == "skipped"  # HOLD
        assert results[2].action == "skipped"  # Weak signal

    @pytest.mark.asyncio
    async def test_strategy_id_forwarded_to_order(self):
        signal = _make_signal(strategy_id="rsi_reversal")

        with (
            patch(
                "tradingsystem.services.order_pipeline.execute_live_trade",
                new_callable=AsyncMock,
            ) as mock_exec,
            patch(
                "tradingsystem.services.order_pipeline.oanda_trading_client"
            ) as mock_client,
        ):
            mock_client.trading_mode = "PAPER"
            mock_order = MagicMock()
            mock_order.id = uuid4()
            mock_position = MagicMock()
            mock_position.id = uuid4()
            mock_response = MagicMock()
            mock_response.price = Decimal("1.0820")
            mock_response.order_id = "oanda-002"
            mock_exec.return_value = (mock_order, mock_position, mock_response)

            await process_signals([signal])

        mock_exec.assert_awaited_once()
        assert mock_exec.call_args[1]["strategy_id"] == "rsi_reversal"
