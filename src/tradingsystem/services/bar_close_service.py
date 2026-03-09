"""Bar close detection service.

Monitors active Series (those with at least one enabled chart strategy)
for new candle appearances. When a new candle is detected, the previous
bar has closed and strategies should be evaluated.

Polls RateService at intervals matching each period's granularity.
Handles forex market hours (closed Fri 5pm–Sun 5pm ET).
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

from tradingsystem.core.database import get_cursor
from tradingsystem.core.rateservice import rateservice_client

logger = logging.getLogger(__name__)

# Polling intervals per period — how often to check for a new bar (seconds).
# Slightly more frequent than the bar duration to catch closes promptly.
PERIOD_POLL_INTERVALS: dict[str, int] = {
    "M1": 15,
    "M5": 30,
    "M15": 60,
    "M30": 120,
    "H1": 180,
    "H4": 600,
    "D": 1800,
}

# Default poll interval for unknown periods
DEFAULT_POLL_INTERVAL = 60


@dataclass
class SeriesState:
    """Tracks the last known candle time for a series."""

    instrument: str
    period: str
    last_candle_time: datetime | None = None
    last_poll_time: datetime | None = None
    consecutive_errors: int = 0


@dataclass
class BarCloseEvent:
    """Emitted when a bar closes on a series."""

    instrument: str
    period: str
    bar_time: datetime
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class BarCloseService:
    """
    Background service that detects completed candles (bar closes).

    Only monitors Series that have at least one Chart with an enabled strategy.
    Polls RateService for the latest candle and compares against the last known
    candle time. A new candle time means the previous bar has closed.
    """

    def __init__(self) -> None:
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._series_states: dict[str, SeriesState] = {}  # key: "instrument:period"
        self._callbacks: list[Callable[[BarCloseEvent], Coroutine[Any, Any, None]]] = []
        self._active_series_refresh_interval = 60  # Re-query active series every 60s
        self._last_active_refresh: datetime | None = None

    @property
    def running(self) -> bool:
        return self._running

    @property
    def monitored_series(self) -> list[dict[str, str]]:
        """Return list of currently monitored series."""
        return [
            {"instrument": s.instrument, "period": s.period}
            for s in self._series_states.values()
        ]

    def on_bar_close(
        self, callback: Callable[[BarCloseEvent], Coroutine[Any, Any, None]]
    ) -> None:
        """Register an async callback for bar close events."""
        self._callbacks.append(callback)

    async def start(self) -> None:
        """Start the bar close detection loop."""
        if self._running:
            logger.warning("Bar close service already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Bar close detection service started")

    async def stop(self) -> None:
        """Stop the bar close detection loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._series_states.clear()
        logger.info("Bar close detection service stopped")

    async def _run_loop(self) -> None:
        """Main loop — polls each active series at its period-appropriate interval."""
        while self._running:
            try:
                await self._refresh_active_series()
                await self._poll_all_series()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Bar close loop error: {e}")

            # Sleep for the shortest poll interval among active series,
            # or a default if no series are active.
            sleep_seconds = self._next_sleep_interval()
            await asyncio.sleep(sleep_seconds)

    async def _refresh_active_series(self) -> None:
        """Query DB for series that have at least one enabled chart strategy."""
        now = datetime.now(timezone.utc)
        if (
            self._last_active_refresh
            and (now - self._last_active_refresh).total_seconds()
            < self._active_series_refresh_interval
        ):
            return

        active = await _get_active_series()
        self._last_active_refresh = now

        # Build set of active keys
        active_keys = {f"{row['instrument']}:{row['period']}" for row in active}

        # Add new series
        for row in active:
            key = f"{row['instrument']}:{row['period']}"
            if key not in self._series_states:
                self._series_states[key] = SeriesState(
                    instrument=row["instrument"],
                    period=row["period"],
                )
                logger.info(f"Monitoring series: {row['instrument']} {row['period']}")

        # Remove series no longer active
        for key in list(self._series_states.keys()):
            if key not in active_keys:
                del self._series_states[key]
                logger.info(f"Stopped monitoring series: {key}")

    async def _poll_all_series(self) -> None:
        """Poll each series if enough time has passed since last poll."""
        now = datetime.now(timezone.utc)

        # Skip during forex market close (Sat 00:00–Sun 21:00 UTC approx)
        if _is_forex_closed(now):
            return

        for state in list(self._series_states.values()):
            interval = PERIOD_POLL_INTERVALS.get(state.period, DEFAULT_POLL_INTERVAL)

            # Check if it's time to poll this series
            if (
                state.last_poll_time
                and (now - state.last_poll_time).total_seconds() < interval
            ):
                continue

            await self._poll_series(state)

    async def _poll_series(self, state: SeriesState) -> None:
        """Fetch the latest candle for a series and check for bar close."""
        state.last_poll_time = datetime.now(timezone.utc)

        try:
            candles = await rateservice_client.get_candles(
                pair=state.instrument,
                period=state.period,
                limit=2,
            )

            if not candles:
                return

            latest = candles[-1]
            latest_time = latest.time

            if state.last_candle_time is None:
                # First poll — seed the state, don't fire an event
                state.last_candle_time = latest_time
                state.consecutive_errors = 0
                return

            if latest_time > state.last_candle_time:
                # New candle appeared — previous bar has closed
                event = BarCloseEvent(
                    instrument=state.instrument,
                    period=state.period,
                    bar_time=state.last_candle_time,
                )
                state.last_candle_time = latest_time
                state.consecutive_errors = 0

                logger.info(
                    f"Bar closed: {state.instrument} {state.period} at {event.bar_time}"
                )

                await self._emit(event)

        except Exception as e:
            state.consecutive_errors += 1
            if state.consecutive_errors <= 3:
                logger.warning(
                    f"Poll error for {state.instrument} {state.period}: {e} "
                    f"(attempt {state.consecutive_errors})"
                )
            elif state.consecutive_errors == 4:
                logger.error(
                    f"Persistent poll errors for {state.instrument} {state.period}, "
                    f"suppressing further warnings"
                )

    async def _emit(self, event: BarCloseEvent) -> None:
        """Fire all registered callbacks for a bar close event."""
        for callback in self._callbacks:
            try:
                await callback(event)
            except Exception as e:
                logger.error(
                    f"Bar close callback error for "
                    f"{event.instrument} {event.period}: {e}"
                )

    def _next_sleep_interval(self) -> float:
        """Calculate shortest sleep interval across all active series."""
        if not self._series_states:
            return 30.0  # No active series — check again in 30s

        intervals = [
            PERIOD_POLL_INTERVALS.get(s.period, DEFAULT_POLL_INTERVAL)
            for s in self._series_states.values()
        ]
        # Sleep for half the shortest interval to stay responsive
        return max(1.0, min(intervals) / 2)

    def get_status(self) -> dict[str, Any]:
        """Return current service status."""
        return {
            "running": self._running,
            "monitored_series": len(self._series_states),
            "series": [
                {
                    "instrument": s.instrument,
                    "period": s.period,
                    "last_candle_time": (
                        s.last_candle_time.isoformat() if s.last_candle_time else None
                    ),
                    "last_poll_time": (
                        s.last_poll_time.isoformat() if s.last_poll_time else None
                    ),
                    "consecutive_errors": s.consecutive_errors,
                }
                for s in self._series_states.values()
            ],
        }


def _is_forex_closed(now: datetime) -> bool:
    """Check if forex market is closed.

    Forex trades ~Sun 21:00 UTC to Fri 21:00 UTC.
    Market is closed Saturday all day and Sunday until ~21:00 UTC.
    """
    weekday = now.weekday()  # 0=Mon, 5=Sat, 6=Sun
    if weekday == 5:
        # Saturday — always closed
        return True
    if weekday == 6 and now.hour < 21:
        # Sunday before 21:00 UTC — still closed
        return True
    if weekday == 4 and now.hour >= 22:
        # Friday after 22:00 UTC — closing (buffer for broker variation)
        return True
    return False


async def _get_active_series() -> list[dict[str, str]]:
    """Query for series that have at least one enabled chart strategy.

    Joins series → charts → chart_strategies to find series where
    at least one chart strategy is enabled.
    """
    async with get_cursor() as cur:
        await cur.execute(
            """
            SELECT DISTINCT s.instrument, s.period
            FROM series s
            JOIN charts c ON c.series_id = s.id
            JOIN chart_strategies cs ON cs.chart_id = c.id
            WHERE cs.enabled = true
            ORDER BY s.instrument, s.period
            """
        )
        rows = await cur.fetchall()
        return [{"instrument": row["instrument"], "period": row["period"]} for row in rows]


# Singleton instance
bar_close_service = BarCloseService()
