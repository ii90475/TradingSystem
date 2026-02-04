"""Tests for signal service."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from tradingsystem.models.signal import Signal, SignalType
from tradingsystem.services import signal_service


# --- Fixtures ---


@pytest.fixture
def sample_signal():
    """Create a sample signal."""
    return Signal(
        id=uuid4(),
        time=datetime.now(timezone.utc),
        strategy_id="ma_crossover",
        instrument="EUR_USD",
        signal_type=SignalType.BUY,
        strength=Decimal("0.85"),
        reason="Bullish crossover",
        metadata={"fast_ma": 1.0860, "slow_ma": 1.0840},
    )


@pytest.fixture
def mock_cursor():
    """Create a mock database cursor."""
    cursor = AsyncMock()
    cursor.fetchone = AsyncMock()
    cursor.fetchall = AsyncMock()
    cursor.execute = AsyncMock()
    cursor.rowcount = 0
    cursor.connection = AsyncMock()
    cursor.connection.commit = AsyncMock()
    return cursor


# --- save_signal Tests ---


class TestSaveSignal:
    """Tests for save_signal function."""

    @pytest.mark.asyncio
    async def test_save_signal_success(self, sample_signal, mock_cursor):
        """Should save signal and return with ID."""
        signal_id = uuid4()
        mock_cursor.fetchone.return_value = {
            "id": signal_id,
            "time": sample_signal.time,
            "strategy_id": sample_signal.strategy_id,
            "instrument": sample_signal.instrument,
            "signal_type": sample_signal.signal_type.value,
            "strength": float(sample_signal.strength),
            "reason": sample_signal.reason,
            "metadata": sample_signal.metadata,
        }

        with patch("tradingsystem.services.signal_service.get_cursor") as mock_get_cursor:
            mock_get_cursor.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await signal_service.save_signal(sample_signal)

            assert result.id == signal_id
            assert result.strategy_id == sample_signal.strategy_id
            assert result.instrument == sample_signal.instrument
            mock_cursor.execute.assert_called_once()
            mock_cursor.connection.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_signal_with_empty_metadata(self, mock_cursor):
        """Should handle empty metadata."""
        signal = Signal(
            time=datetime.now(timezone.utc),
            strategy_id="test",
            instrument="EUR_USD",
            signal_type=SignalType.BUY,
            metadata={},
        )
        signal_id = uuid4()
        mock_cursor.fetchone.return_value = {
            "id": signal_id,
            "time": signal.time,
            "strategy_id": signal.strategy_id,
            "instrument": signal.instrument,
            "signal_type": signal.signal_type.value,
            "strength": 0.5,  # Provide valid strength value
            "reason": "Test",
            "metadata": None,  # DB returns NULL for empty metadata
        }

        with patch("tradingsystem.services.signal_service.get_cursor") as mock_get_cursor:
            mock_get_cursor.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await signal_service.save_signal(signal)

            assert result.metadata == {}  # Service converts NULL to empty dict


# --- save_signals Tests ---


class TestSaveSignals:
    """Tests for save_signals function."""

    @pytest.mark.asyncio
    async def test_save_signals_multiple(self, mock_cursor):
        """Should save multiple signals."""
        signals = [
            Signal(
                time=datetime.now(timezone.utc),
                strategy_id="test",
                instrument="EUR_USD",
                signal_type=SignalType.BUY,
            ),
            Signal(
                time=datetime.now(timezone.utc),
                strategy_id="test",
                instrument="GBP_USD",
                signal_type=SignalType.SELL,
            ),
        ]

        with patch("tradingsystem.services.signal_service.save_signal") as mock_save:
            mock_save.side_effect = signals

            result = await signal_service.save_signals(signals)

            assert len(result) == 2
            assert mock_save.call_count == 2


# --- get_signal Tests ---


class TestGetSignal:
    """Tests for get_signal function."""

    @pytest.mark.asyncio
    async def test_get_signal_found(self, mock_cursor):
        """Should return signal when found."""
        signal_id = uuid4()
        mock_cursor.fetchone.return_value = {
            "id": signal_id,
            "time": datetime.now(timezone.utc),
            "strategy_id": "ma_crossover",
            "instrument": "EUR_USD",
            "signal_type": "BUY",
            "strength": 0.85,
            "reason": "Test",
            "metadata": {"key": "value"},
        }

        with patch("tradingsystem.services.signal_service.get_cursor") as mock_get_cursor:
            mock_get_cursor.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await signal_service.get_signal(signal_id)

            assert result is not None
            assert result.id == signal_id
            assert result.signal_type == SignalType.BUY

    @pytest.mark.asyncio
    async def test_get_signal_not_found(self, mock_cursor):
        """Should return None when not found."""
        mock_cursor.fetchone.return_value = None

        with patch("tradingsystem.services.signal_service.get_cursor") as mock_get_cursor:
            mock_get_cursor.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await signal_service.get_signal(uuid4())

            assert result is None


# --- list_signals Tests ---


class TestListSignals:
    """Tests for list_signals function."""

    @pytest.mark.asyncio
    async def test_list_signals_no_filters(self, mock_cursor):
        """Should list all signals when no filters."""
        mock_cursor.fetchall.return_value = [
            {
                "id": uuid4(),
                "time": datetime.now(timezone.utc),
                "strategy_id": "ma_crossover",
                "instrument": "EUR_USD",
                "signal_type": "BUY",
                "strength": 0.85,
                "reason": "Test",
                "metadata": {},
            }
        ]

        with patch("tradingsystem.services.signal_service.get_cursor") as mock_get_cursor:
            mock_get_cursor.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await signal_service.list_signals()

            assert len(result) == 1
            assert result[0].signal_type == SignalType.BUY

    @pytest.mark.asyncio
    async def test_list_signals_filter_by_strategy(self, mock_cursor):
        """Should filter by strategy_id."""
        mock_cursor.fetchall.return_value = []

        with patch("tradingsystem.services.signal_service.get_cursor") as mock_get_cursor:
            mock_get_cursor.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__aexit__ = AsyncMock(return_value=False)

            await signal_service.list_signals(strategy_id="ma_crossover")

            call_args = mock_cursor.execute.call_args
            assert "strategy_id = %s" in call_args[0][0]
            assert "ma_crossover" in call_args[0][1]

    @pytest.mark.asyncio
    async def test_list_signals_filter_by_instrument(self, mock_cursor):
        """Should filter by instrument."""
        mock_cursor.fetchall.return_value = []

        with patch("tradingsystem.services.signal_service.get_cursor") as mock_get_cursor:
            mock_get_cursor.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__aexit__ = AsyncMock(return_value=False)

            await signal_service.list_signals(instrument="EUR_USD")

            call_args = mock_cursor.execute.call_args
            assert "instrument = %s" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_list_signals_filter_by_type(self, mock_cursor):
        """Should filter by signal type."""
        mock_cursor.fetchall.return_value = []

        with patch("tradingsystem.services.signal_service.get_cursor") as mock_get_cursor:
            mock_get_cursor.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__aexit__ = AsyncMock(return_value=False)

            await signal_service.list_signals(signal_type=SignalType.SELL)

            call_args = mock_cursor.execute.call_args
            assert "signal_type = %s" in call_args[0][0]
            assert "SELL" in call_args[0][1]

    @pytest.mark.asyncio
    async def test_list_signals_filter_by_time_range(self, mock_cursor):
        """Should filter by time range."""
        mock_cursor.fetchall.return_value = []
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 31, tzinfo=timezone.utc)

        with patch("tradingsystem.services.signal_service.get_cursor") as mock_get_cursor:
            mock_get_cursor.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__aexit__ = AsyncMock(return_value=False)

            await signal_service.list_signals(start=start, end=end)

            call_args = mock_cursor.execute.call_args
            assert "time >= %s" in call_args[0][0]
            assert "time <= %s" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_list_signals_pagination(self, mock_cursor):
        """Should apply limit and offset."""
        mock_cursor.fetchall.return_value = []

        with patch("tradingsystem.services.signal_service.get_cursor") as mock_get_cursor:
            mock_get_cursor.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__aexit__ = AsyncMock(return_value=False)

            await signal_service.list_signals(limit=50, offset=10)

            call_args = mock_cursor.execute.call_args
            assert "LIMIT %s OFFSET %s" in call_args[0][0]
            assert 50 in call_args[0][1]
            assert 10 in call_args[0][1]


# --- count_signals Tests ---


class TestCountSignals:
    """Tests for count_signals function."""

    @pytest.mark.asyncio
    async def test_count_signals_no_filter(self, mock_cursor):
        """Should count all signals."""
        mock_cursor.fetchone.return_value = {"count": 42}

        with patch("tradingsystem.services.signal_service.get_cursor") as mock_get_cursor:
            mock_get_cursor.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await signal_service.count_signals()

            assert result == 42

    @pytest.mark.asyncio
    async def test_count_signals_with_filters(self, mock_cursor):
        """Should count filtered signals."""
        mock_cursor.fetchone.return_value = {"count": 10}

        with patch("tradingsystem.services.signal_service.get_cursor") as mock_get_cursor:
            mock_get_cursor.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await signal_service.count_signals(
                strategy_id="ma_crossover",
                instrument="EUR_USD",
            )

            assert result == 10
            call_args = mock_cursor.execute.call_args
            assert "strategy_id = %s" in call_args[0][0]
            assert "instrument = %s" in call_args[0][0]


# --- get_latest_signals Tests ---


class TestGetLatestSignals:
    """Tests for get_latest_signals function."""

    @pytest.mark.asyncio
    async def test_get_latest_signals(self):
        """Should call list_signals with limit."""
        with patch("tradingsystem.services.signal_service.list_signals") as mock_list:
            mock_list.return_value = []

            await signal_service.get_latest_signals(limit=5)

            mock_list.assert_called_once_with(strategy_id=None, limit=5)


# --- get_signals_by_strategy Tests ---


class TestGetSignalsByStrategy:
    """Tests for get_signals_by_strategy function."""

    @pytest.mark.asyncio
    async def test_get_signals_by_strategy(self):
        """Should filter by strategy."""
        with patch("tradingsystem.services.signal_service.list_signals") as mock_list:
            mock_list.return_value = []

            await signal_service.get_signals_by_strategy("ma_crossover", limit=50)

            mock_list.assert_called_once_with(strategy_id="ma_crossover", limit=50)


# --- delete_old_signals Tests ---


class TestDeleteOldSignals:
    """Tests for delete_old_signals function."""

    @pytest.mark.asyncio
    async def test_delete_old_signals(self, mock_cursor):
        """Should delete signals older than specified days."""
        mock_cursor.rowcount = 15

        with patch("tradingsystem.services.signal_service.get_cursor") as mock_get_cursor:
            mock_get_cursor.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await signal_service.delete_old_signals(days=30)

            assert result == 15
            mock_cursor.connection.commit.assert_called_once()
            call_args = mock_cursor.execute.call_args
            assert "DELETE FROM signals" in call_args[0][0]
            assert 30 in call_args[0][1]

    @pytest.mark.asyncio
    async def test_delete_old_signals_none_deleted(self, mock_cursor):
        """Should return 0 when nothing to delete."""
        mock_cursor.rowcount = 0

        with patch("tradingsystem.services.signal_service.get_cursor") as mock_get_cursor:
            mock_get_cursor.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await signal_service.delete_old_signals(days=7)

            assert result == 0
