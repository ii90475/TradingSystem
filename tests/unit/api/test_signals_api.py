"""Tests for signals API endpoints."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from tradingsystem.api.signals import (
    cleanup_old_signals,
    count_signals,
    get_latest_signals,
    get_signal,
    get_signals_by_strategy,
    list_signals,
)
from tradingsystem.models.signal import Signal, SignalType


# --- Fixtures ---


@pytest.fixture
def sample_signal():
    """Create sample signal."""
    return Signal(
        id=uuid4(),
        strategy_id="ma_crossover",
        instrument="EUR_USD",
        signal_type=SignalType.BUY,
        strength=Decimal("0.8"),
        reason="Golden cross detected",
        time=datetime.now(timezone.utc),
    )


# --- list_signals Tests ---


class TestListSignals:
    """Tests for list_signals endpoint."""

    @pytest.mark.asyncio
    async def test_returns_signals(self, sample_signal):
        """Should return list of signals."""
        with patch("tradingsystem.api.signals.signal_service") as mock_service:
            mock_service.list_signals = AsyncMock(return_value=[sample_signal])

            result = await list_signals(
                strategy_id=None,
                instrument=None,
                signal_type=None,
                start=None,
                end=None,
                limit=100,
                offset=0,
            )

            assert len(result) == 1
            assert result[0].instrument == "EUR_USD"

    @pytest.mark.asyncio
    async def test_passes_all_filters(self, sample_signal):
        """Should pass all filter parameters."""
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 31, tzinfo=timezone.utc)

        with patch("tradingsystem.api.signals.signal_service") as mock_service:
            mock_service.list_signals = AsyncMock(return_value=[sample_signal])

            await list_signals(
                strategy_id="test_strategy",
                instrument="EUR_USD",
                signal_type=SignalType.BUY,
                start=start,
                end=end,
                limit=50,
                offset=10,
            )

            mock_service.list_signals.assert_called_once_with(
                strategy_id="test_strategy",
                instrument="EUR_USD",
                signal_type=SignalType.BUY,
                start=start,
                end=end,
                limit=50,
                offset=10,
            )

    @pytest.mark.asyncio
    async def test_returns_empty_list(self):
        """Should return empty list when no signals."""
        with patch("tradingsystem.api.signals.signal_service") as mock_service:
            mock_service.list_signals = AsyncMock(return_value=[])

            result = await list_signals(
                strategy_id=None,
                instrument=None,
                signal_type=None,
                start=None,
                end=None,
                limit=100,
                offset=0,
            )

            assert result == []


# --- count_signals Tests ---


class TestCountSignals:
    """Tests for count_signals endpoint."""

    @pytest.mark.asyncio
    async def test_returns_count(self):
        """Should return signal count."""
        with patch("tradingsystem.api.signals.signal_service") as mock_service:
            mock_service.count_signals = AsyncMock(return_value=42)

            result = await count_signals(
                strategy_id=None,
                instrument=None,
                signal_type=None,
                start=None,
                end=None,
            )

            assert result == {"count": 42}

    @pytest.mark.asyncio
    async def test_passes_filters(self):
        """Should pass filter parameters."""
        with patch("tradingsystem.api.signals.signal_service") as mock_service:
            mock_service.count_signals = AsyncMock(return_value=10)

            await count_signals(
                strategy_id="test",
                instrument="EUR_USD",
                signal_type=SignalType.SELL,
                start=None,
                end=None,
            )

            mock_service.count_signals.assert_called_once_with(
                strategy_id="test",
                instrument="EUR_USD",
                signal_type=SignalType.SELL,
                start=None,
                end=None,
            )


# --- get_latest_signals Tests ---


class TestGetLatestSignals:
    """Tests for get_latest_signals endpoint."""

    @pytest.mark.asyncio
    async def test_returns_latest(self, sample_signal):
        """Should return latest signals."""
        with patch("tradingsystem.api.signals.signal_service") as mock_service:
            mock_service.get_latest_signals = AsyncMock(return_value=[sample_signal])

            result = await get_latest_signals(strategy_id=None, limit=10)

            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_filters_by_strategy(self, sample_signal):
        """Should filter by strategy ID."""
        with patch("tradingsystem.api.signals.signal_service") as mock_service:
            mock_service.get_latest_signals = AsyncMock(return_value=[sample_signal])

            await get_latest_signals(strategy_id="ma_crossover", limit=5)

            mock_service.get_latest_signals.assert_called_once_with(
                strategy_id="ma_crossover",
                limit=5,
            )


# --- get_signal Tests ---


class TestGetSignal:
    """Tests for get_signal endpoint."""

    @pytest.mark.asyncio
    async def test_returns_signal(self, sample_signal):
        """Should return signal by ID."""
        with patch("tradingsystem.api.signals.signal_service") as mock_service:
            mock_service.get_signal = AsyncMock(return_value=sample_signal)

            result = await get_signal(sample_signal.id)

            assert result.id == sample_signal.id

    @pytest.mark.asyncio
    async def test_raises_404_when_not_found(self):
        """Should raise 404 when signal not found."""
        with patch("tradingsystem.api.signals.signal_service") as mock_service:
            mock_service.get_signal = AsyncMock(return_value=None)

            with pytest.raises(HTTPException) as exc_info:
                await get_signal(uuid4())

            assert exc_info.value.status_code == 404
            assert "not found" in exc_info.value.detail.lower()


# --- get_signals_by_strategy Tests ---


class TestGetSignalsByStrategy:
    """Tests for get_signals_by_strategy endpoint."""

    @pytest.mark.asyncio
    async def test_returns_strategy_signals(self, sample_signal):
        """Should return signals for strategy."""
        with patch("tradingsystem.api.signals.signal_service") as mock_service:
            mock_service.get_signals_by_strategy = AsyncMock(return_value=[sample_signal])

            result = await get_signals_by_strategy(strategy_id="ma_crossover", limit=100)

            assert len(result) == 1
            assert result[0].strategy_id == "ma_crossover"

    @pytest.mark.asyncio
    async def test_passes_limit(self, sample_signal):
        """Should pass limit parameter."""
        with patch("tradingsystem.api.signals.signal_service") as mock_service:
            mock_service.get_signals_by_strategy = AsyncMock(return_value=[sample_signal])

            await get_signals_by_strategy(strategy_id="test", limit=50)

            mock_service.get_signals_by_strategy.assert_called_once_with(
                strategy_id="test",
                limit=50,
            )


# --- cleanup_old_signals Tests ---


class TestCleanupOldSignals:
    """Tests for cleanup_old_signals endpoint."""

    @pytest.mark.asyncio
    async def test_deletes_old_signals(self):
        """Should delete old signals and return count."""
        with patch("tradingsystem.api.signals.signal_service") as mock_service:
            mock_service.delete_old_signals = AsyncMock(return_value=15)

            result = await cleanup_old_signals(days=30)

            assert result["status"] == "success"
            assert result["deleted"] == 15
            assert result["days_threshold"] == 30

    @pytest.mark.asyncio
    async def test_uses_provided_days(self):
        """Should use provided days threshold."""
        with patch("tradingsystem.api.signals.signal_service") as mock_service:
            mock_service.delete_old_signals = AsyncMock(return_value=5)

            await cleanup_old_signals(days=7)

            mock_service.delete_old_signals.assert_called_once_with(days=7)

    @pytest.mark.asyncio
    async def test_returns_zero_when_none_deleted(self):
        """Should return zero when no signals deleted."""
        with patch("tradingsystem.api.signals.signal_service") as mock_service:
            mock_service.delete_old_signals = AsyncMock(return_value=0)

            result = await cleanup_old_signals(days=30)

            assert result["deleted"] == 0
