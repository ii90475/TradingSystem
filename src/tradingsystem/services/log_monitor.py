"""Log monitoring handler for error/warning rate detection."""

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field

from tradingsystem.core.config import settings
from tradingsystem.services.alert_service import (
    AlertLevel,
    AlertType,
    alert_service,
)

logger = logging.getLogger(__name__)


@dataclass
class LogStats:
    """Statistics about log messages in the monitoring window."""

    error_count: int = 0
    warning_count: int = 0
    window_seconds: int = 300
    error_threshold: int = 10
    warning_threshold: int = 50
    error_rate_exceeded: bool = False
    warning_rate_exceeded: bool = False


class LogMonitorHandler(logging.Handler):
    """
    Logging handler that tracks error/warning rates in a sliding window.

    Alerts when the count of errors or warnings exceeds configurable thresholds.
    Thread-safe implementation for use across the application.
    """

    def __init__(
        self,
        window_seconds: int | None = None,
        error_threshold: int | None = None,
        warning_threshold: int | None = None,
    ) -> None:
        super().__init__()

        self._window_seconds = window_seconds or settings.log_monitor_window_seconds
        self._error_threshold = error_threshold or settings.log_monitor_error_threshold
        self._warning_threshold = warning_threshold or settings.log_monitor_warning_threshold

        # Thread-safe collections for timestamps
        self._lock = threading.Lock()
        self._errors: deque[float] = deque()
        self._warnings: deque[float] = deque()

        # Track if we've already alerted for current spike
        self._error_alert_active = False
        self._warning_alert_active = False

    def emit(self, record: logging.LogRecord) -> None:
        """
        Process a log record.

        Args:
            record: The log record to process
        """
        now = time.time()

        with self._lock:
            # Prune old entries
            self._prune_old_entries(now)

            # Track errors and warnings
            if record.levelno >= logging.ERROR:
                self._errors.append(now)
                self._check_error_threshold()
            elif record.levelno >= logging.WARNING:
                self._warnings.append(now)
                self._check_warning_threshold()

    def _prune_old_entries(self, now: float) -> None:
        """Remove entries outside the sliding window."""
        cutoff = now - self._window_seconds

        while self._errors and self._errors[0] < cutoff:
            self._errors.popleft()

        while self._warnings and self._warnings[0] < cutoff:
            self._warnings.popleft()

    def _check_error_threshold(self) -> None:
        """Check if error threshold is exceeded and alert if needed."""
        error_count = len(self._errors)

        if error_count >= self._error_threshold and not self._error_alert_active:
            self._error_alert_active = True
            alert_service.create_alert(
                AlertType.LOG_RATE_EXCEEDED,
                AlertLevel.CRITICAL,
                f"Error rate exceeded: {error_count} errors in {self._window_seconds}s window",
                {
                    "error_count": error_count,
                    "threshold": self._error_threshold,
                    "window_seconds": self._window_seconds,
                },
            )
        elif error_count < self._error_threshold and self._error_alert_active:
            # Reset alert state when back below threshold
            self._error_alert_active = False

    def _check_warning_threshold(self) -> None:
        """Check if warning threshold is exceeded and alert if needed."""
        warning_count = len(self._warnings)

        if warning_count >= self._warning_threshold and not self._warning_alert_active:
            self._warning_alert_active = True
            alert_service.create_alert(
                AlertType.LOG_RATE_EXCEEDED,
                AlertLevel.WARNING,
                f"Warning rate exceeded: {warning_count} warnings in {self._window_seconds}s window",
                {
                    "warning_count": warning_count,
                    "threshold": self._warning_threshold,
                    "window_seconds": self._window_seconds,
                },
            )
        elif warning_count < self._warning_threshold and self._warning_alert_active:
            # Reset alert state when back below threshold
            self._warning_alert_active = False

    def get_stats(self) -> LogStats:
        """
        Get current log statistics.

        Returns:
            LogStats with current counts and thresholds
        """
        now = time.time()

        with self._lock:
            self._prune_old_entries(now)
            return LogStats(
                error_count=len(self._errors),
                warning_count=len(self._warnings),
                window_seconds=self._window_seconds,
                error_threshold=self._error_threshold,
                warning_threshold=self._warning_threshold,
                error_rate_exceeded=self._error_alert_active,
                warning_rate_exceeded=self._warning_alert_active,
            )

    def reset(self) -> None:
        """Reset all counters and alert states."""
        with self._lock:
            self._errors.clear()
            self._warnings.clear()
            self._error_alert_active = False
            self._warning_alert_active = False


# Singleton instance
_log_monitor_handler: LogMonitorHandler | None = None


def setup_log_monitoring() -> LogMonitorHandler:
    """
    Set up log monitoring by attaching handler to the root logger.

    Returns:
        The LogMonitorHandler instance
    """
    global _log_monitor_handler

    if _log_monitor_handler is not None:
        return _log_monitor_handler

    _log_monitor_handler = LogMonitorHandler()
    logging.getLogger().addHandler(_log_monitor_handler)

    logger.info(
        "Log monitoring initialized",
        extra={
            "window_seconds": settings.log_monitor_window_seconds,
            "error_threshold": settings.log_monitor_error_threshold,
            "warning_threshold": settings.log_monitor_warning_threshold,
        },
    )

    return _log_monitor_handler


def get_log_monitor() -> LogMonitorHandler | None:
    """Get the log monitor handler instance."""
    return _log_monitor_handler
