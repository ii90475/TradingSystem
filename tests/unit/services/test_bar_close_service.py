"""Tests for bar close detection service."""

from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tradingsystem.services.bar_close_service import (
    BarCloseEvent,
    BarCloseService,
    SeriesState,
    _is_forex_closed,
    _get_active_series,
    PERIOD_POLL_INTERVALS,
)


# --- SeriesState Tests ---


class TestSeriesState:
    """Tests for SeriesState dataclass."""

    def test_default_values(self):
        state = SeriesState(instrument="EUR_USD", period="H1")
        assert state.instrument == "EUR_USD"
        assert state.period == "H1"
        assert state.last_candle_time is None
        assert state.last_poll_time is None
        assert state.consecutive_errors == 0


# --- BarCloseEvent Tests ---


class TestBarCloseEvent:
    """Tests for BarCloseEvent dataclass."""

    def test_creation(self):
        bar_time = datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc)
        event = BarCloseEvent(instrument="EUR_USD", period="H1", bar_time=bar_time)
        assert event.instrument == "EUR_USD"
        assert event.period == "H1"
        assert event.bar_time == bar_time
        assert event.detected_at is not None


# --- Forex Market Hours Tests ---


class TestIsForexClosed:
    """Tests for _is_forex_closed helper."""

    def test_monday_open(self):
        # Monday 10:00 UTC — market open
        dt = datetime(2026, 3, 9, 10, 0, tzinfo=timezone.utc)  # Monday
        assert dt.weekday() == 0
        assert _is_forex_closed(dt) is False

    def test_friday_afternoon_open(self):
        # Friday 15:00 UTC — market open
        dt = datetime(2026, 3, 13, 15, 0, tzinfo=timezone.utc)  # Friday
        assert dt.weekday() == 4
        assert _is_forex_closed(dt) is False

    def test_friday_late_closed(self):
        # Friday 22:30 UTC — market closing
        dt = datetime(2026, 3, 13, 22, 30, tzinfo=timezone.utc)  # Friday
        assert _is_forex_closed(dt) is True

    def test_saturday_closed(self):
        # Saturday — always closed
        dt = datetime(2026, 3, 14, 12, 0, tzinfo=timezone.utc)  # Saturday
        assert dt.weekday() == 5
        assert _is_forex_closed(dt) is True

    def test_sunday_before_open_closed(self):
        # Sunday 15:00 UTC — still closed
        dt = datetime(2026, 3, 15, 15, 0, tzinfo=timezone.utc)  # Sunday
        assert dt.weekday() == 6
        assert _is_forex_closed(dt) is True

    def test_sunday_after_open(self):
        # Sunday 21:30 UTC — market open
        dt = datetime(2026, 3, 15, 21, 30, tzinfo=timezone.utc)  # Sunday
        assert _is_forex_closed(dt) is False


# --- BarCloseService Tests ---


class TestBarCloseService:
    """Tests for BarCloseService."""

    def test_initial_state(self):
        service = BarCloseService()
        assert service.running is False
        assert service.monitored_series == []

    def test_callback_registration(self):
        service = BarCloseService()
        callback = AsyncMock()
        service.on_bar_close(callback)
        assert callback in service._callbacks

    @pytest.mark.asyncio
    async def test_start_and_stop(self):
        service = BarCloseService()

        with patch.object(service, "_run_loop", new_callable=AsyncMock):
            await service.start()
            assert service.running is True

            await service.stop()
            assert service.running is False
            assert service._series_states == {}

    @pytest.mark.asyncio
    async def test_start_idempotent(self):
        service = BarCloseService()

        with patch.object(service, "_run_loop", new_callable=AsyncMock):
            await service.start()
            task1 = service._task
            await service.start()  # Should warn, not create new task
            assert service._task is task1
            await service.stop()

    @pytest.mark.asyncio
    async def test_emit_calls_callbacks(self):
        service = BarCloseService()
        callback1 = AsyncMock()
        callback2 = AsyncMock()
        service.on_bar_close(callback1)
        service.on_bar_close(callback2)

        event = BarCloseEvent(
            instrument="EUR_USD",
            period="H1",
            bar_time=datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc),
        )

        await service._emit(event)

        callback1.assert_awaited_once_with(event)
        callback2.assert_awaited_once_with(event)

    @pytest.mark.asyncio
    async def test_emit_handles_callback_error(self):
        service = BarCloseService()
        bad_callback = AsyncMock(side_effect=RuntimeError("boom"))
        good_callback = AsyncMock()
        service.on_bar_close(bad_callback)
        service.on_bar_close(good_callback)

        event = BarCloseEvent(
            instrument="EUR_USD",
            period="H1",
            bar_time=datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc),
        )

        await service._emit(event)

        # Good callback should still be called despite bad one failing
        good_callback.assert_awaited_once_with(event)

    @pytest.mark.asyncio
    async def test_poll_series_first_poll_seeds_state(self):
        """First poll should set last_candle_time but not emit an event."""
        service = BarCloseService()
        callback = AsyncMock()
        service.on_bar_close(callback)

        state = SeriesState(instrument="EUR_USD", period="H1")

        candle_time = datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc)
        mock_candle = MagicMock()
        mock_candle.time = candle_time

        with patch(
            "tradingsystem.services.bar_close_service.rateservice_client"
        ) as mock_rs:
            mock_rs.get_candles = AsyncMock(return_value=[mock_candle])
            await service._poll_series(state)

        assert state.last_candle_time == candle_time
        callback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_poll_series_detects_new_bar(self):
        """When a new candle appears, emit a bar close event."""
        service = BarCloseService()
        callback = AsyncMock()
        service.on_bar_close(callback)

        old_time = datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc)
        new_time = datetime(2026, 3, 9, 13, 0, tzinfo=timezone.utc)

        state = SeriesState(
            instrument="EUR_USD",
            period="H1",
            last_candle_time=old_time,
        )

        mock_candle = MagicMock()
        mock_candle.time = new_time

        with patch(
            "tradingsystem.services.bar_close_service.rateservice_client"
        ) as mock_rs:
            mock_rs.get_candles = AsyncMock(return_value=[mock_candle])
            await service._poll_series(state)

        assert state.last_candle_time == new_time
        callback.assert_awaited_once()
        event = callback.call_args[0][0]
        assert event.instrument == "EUR_USD"
        assert event.period == "H1"
        assert event.bar_time == old_time  # The closed bar's time

    @pytest.mark.asyncio
    async def test_poll_series_no_new_bar(self):
        """Same candle time — no event emitted."""
        service = BarCloseService()
        callback = AsyncMock()
        service.on_bar_close(callback)

        candle_time = datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc)
        state = SeriesState(
            instrument="EUR_USD",
            period="H1",
            last_candle_time=candle_time,
        )

        mock_candle = MagicMock()
        mock_candle.time = candle_time

        with patch(
            "tradingsystem.services.bar_close_service.rateservice_client"
        ) as mock_rs:
            mock_rs.get_candles = AsyncMock(return_value=[mock_candle])
            await service._poll_series(state)

        callback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_poll_series_handles_error(self):
        """Errors increment consecutive_errors counter."""
        service = BarCloseService()
        state = SeriesState(instrument="EUR_USD", period="H1")

        with patch(
            "tradingsystem.services.bar_close_service.rateservice_client"
        ) as mock_rs:
            mock_rs.get_candles = AsyncMock(side_effect=ConnectionError("offline"))
            await service._poll_series(state)

        assert state.consecutive_errors == 1

    @pytest.mark.asyncio
    async def test_poll_series_empty_candles(self):
        """Empty candle response — no crash, no event."""
        service = BarCloseService()
        state = SeriesState(instrument="EUR_USD", period="H1")

        with patch(
            "tradingsystem.services.bar_close_service.rateservice_client"
        ) as mock_rs:
            mock_rs.get_candles = AsyncMock(return_value=[])
            await service._poll_series(state)

        assert state.last_candle_time is None

    def test_next_sleep_interval_no_series(self):
        service = BarCloseService()
        assert service._next_sleep_interval() == 30.0

    def test_next_sleep_interval_with_m1(self):
        service = BarCloseService()
        service._series_states["EUR_USD:M1"] = SeriesState(
            instrument="EUR_USD", period="M1"
        )
        # M1 poll interval is 15s, sleep should be 7.5s
        assert service._next_sleep_interval() == 7.5

    def test_get_status(self):
        service = BarCloseService()
        service._running = True
        state = SeriesState(
            instrument="EUR_USD",
            period="H1",
            last_candle_time=datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc),
        )
        service._series_states["EUR_USD:H1"] = state

        status = service.get_status()
        assert status["running"] is True
        assert status["monitored_series"] == 1
        assert len(status["series"]) == 1
        assert status["series"][0]["instrument"] == "EUR_USD"

    @pytest.mark.asyncio
    async def test_refresh_active_series_adds_new(self):
        service = BarCloseService()

        with patch(
            "tradingsystem.services.bar_close_service._get_active_series",
            new_callable=AsyncMock,
            return_value=[{"instrument": "EUR_USD", "period": "H1"}],
        ):
            await service._refresh_active_series()

        assert "EUR_USD:H1" in service._series_states

    @pytest.mark.asyncio
    async def test_refresh_active_series_removes_inactive(self):
        service = BarCloseService()
        service._series_states["GBP_USD:M5"] = SeriesState(
            instrument="GBP_USD", period="M5"
        )

        with patch(
            "tradingsystem.services.bar_close_service._get_active_series",
            new_callable=AsyncMock,
            return_value=[{"instrument": "EUR_USD", "period": "H1"}],
        ):
            await service._refresh_active_series()

        assert "GBP_USD:M5" not in service._series_states
        assert "EUR_USD:H1" in service._series_states

    @pytest.mark.asyncio
    async def test_refresh_skips_if_recent(self):
        service = BarCloseService()
        service._last_active_refresh = datetime.now(timezone.utc)

        with patch(
            "tradingsystem.services.bar_close_service._get_active_series",
            new_callable=AsyncMock,
        ) as mock_get:
            await service._refresh_active_series()

        mock_get.assert_not_awaited()


# --- Active Series Query Tests ---


class TestGetActiveSeries:
    """Tests for _get_active_series DB query."""

    @pytest.mark.asyncio
    async def test_returns_active_series(self):
        mock_cursor = AsyncMock()
        mock_cursor.fetchall = AsyncMock(
            return_value=[
                {"instrument": "EUR_USD", "period": "H1"},
                {"instrument": "GBP_USD", "period": "M15"},
            ]
        )
        mock_cursor.connection = MagicMock()

        with patch(
            "tradingsystem.services.bar_close_service.get_cursor"
        ) as mock_get_cursor:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_get_cursor.return_value = mock_ctx

            result = await _get_active_series()

        assert len(result) == 2
        assert result[0] == {"instrument": "EUR_USD", "period": "H1"}

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_active(self):
        mock_cursor = AsyncMock()
        mock_cursor.fetchall = AsyncMock(return_value=[])
        mock_cursor.connection = MagicMock()

        with patch(
            "tradingsystem.services.bar_close_service.get_cursor"
        ) as mock_get_cursor:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_get_cursor.return_value = mock_ctx

            result = await _get_active_series()

        assert result == []


# --- Poll Interval Config Tests ---


class TestPollIntervals:
    """Tests for period poll interval configuration."""

    def test_all_standard_periods_have_intervals(self):
        for period in ["M1", "M5", "M15", "M30", "H1", "H4", "D"]:
            assert period in PERIOD_POLL_INTERVALS

    def test_shorter_periods_poll_more_frequently(self):
        assert PERIOD_POLL_INTERVALS["M1"] < PERIOD_POLL_INTERVALS["H1"]
        assert PERIOD_POLL_INTERVALS["H1"] < PERIOD_POLL_INTERVALS["D"]
