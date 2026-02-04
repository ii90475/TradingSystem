"""Tests for log monitoring service."""

import logging
import time
from unittest.mock import MagicMock, patch

import pytest

from tradingsystem.services.log_monitor import (
    LogMonitorHandler,
    LogStats,
    get_log_monitor,
    setup_log_monitoring,
)


# --- LogStats Tests ---


class TestLogStats:
    """Tests for LogStats dataclass."""

    def test_default_values(self):
        """Should have sensible defaults."""
        stats = LogStats()

        assert stats.error_count == 0
        assert stats.warning_count == 0
        assert stats.window_seconds == 300
        assert stats.error_threshold == 10
        assert stats.warning_threshold == 50
        assert stats.error_rate_exceeded is False
        assert stats.warning_rate_exceeded is False

    def test_custom_values(self):
        """Should accept custom values."""
        stats = LogStats(
            error_count=5,
            warning_count=20,
            window_seconds=600,
            error_threshold=15,
            warning_threshold=100,
            error_rate_exceeded=True,
            warning_rate_exceeded=False,
        )

        assert stats.error_count == 5
        assert stats.warning_count == 20
        assert stats.window_seconds == 600
        assert stats.error_threshold == 15
        assert stats.warning_threshold == 100
        assert stats.error_rate_exceeded is True
        assert stats.warning_rate_exceeded is False


# --- LogMonitorHandler Tests ---


class TestLogMonitorHandlerInit:
    """Tests for LogMonitorHandler initialization."""

    def test_default_thresholds(self):
        """Should use settings values by default."""
        with patch("tradingsystem.services.log_monitor.settings") as mock_settings:
            mock_settings.log_monitor_window_seconds = 300
            mock_settings.log_monitor_error_threshold = 10
            mock_settings.log_monitor_warning_threshold = 50

            handler = LogMonitorHandler()

            assert handler._window_seconds == 300
            assert handler._error_threshold == 10
            assert handler._warning_threshold == 50

    def test_custom_thresholds(self):
        """Should accept custom thresholds."""
        handler = LogMonitorHandler(
            window_seconds=600,
            error_threshold=5,
            warning_threshold=25,
        )

        assert handler._window_seconds == 600
        assert handler._error_threshold == 5
        assert handler._warning_threshold == 25

    def test_initializes_empty_collections(self):
        """Should start with empty error/warning collections."""
        handler = LogMonitorHandler(window_seconds=300, error_threshold=10, warning_threshold=50)

        assert len(handler._errors) == 0
        assert len(handler._warnings) == 0

    def test_alert_states_initially_false(self):
        """Should start with alert states as False."""
        handler = LogMonitorHandler(window_seconds=300, error_threshold=10, warning_threshold=50)

        assert handler._error_alert_active is False
        assert handler._warning_alert_active is False


class TestLogMonitorHandlerEmit:
    """Tests for LogMonitorHandler.emit method."""

    @pytest.fixture
    def handler(self):
        """Create handler with low thresholds for testing."""
        return LogMonitorHandler(
            window_seconds=300,
            error_threshold=3,
            warning_threshold=5,
        )

    def test_tracks_error_level(self, handler):
        """Should track ERROR level logs."""
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="Test error",
            args=(),
            exc_info=None,
        )

        handler.emit(record)

        assert len(handler._errors) == 1
        assert len(handler._warnings) == 0

    def test_tracks_critical_level_as_error(self, handler):
        """Should track CRITICAL level as error."""
        record = logging.LogRecord(
            name="test",
            level=logging.CRITICAL,
            pathname="",
            lineno=0,
            msg="Test critical",
            args=(),
            exc_info=None,
        )

        handler.emit(record)

        assert len(handler._errors) == 1

    def test_tracks_warning_level(self, handler):
        """Should track WARNING level logs."""
        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname="",
            lineno=0,
            msg="Test warning",
            args=(),
            exc_info=None,
        )

        handler.emit(record)

        assert len(handler._warnings) == 1
        assert len(handler._errors) == 0

    def test_ignores_info_level(self, handler):
        """Should ignore INFO level logs."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test info",
            args=(),
            exc_info=None,
        )

        handler.emit(record)

        assert len(handler._errors) == 0
        assert len(handler._warnings) == 0

    def test_ignores_debug_level(self, handler):
        """Should ignore DEBUG level logs."""
        record = logging.LogRecord(
            name="test",
            level=logging.DEBUG,
            pathname="",
            lineno=0,
            msg="Test debug",
            args=(),
            exc_info=None,
        )

        handler.emit(record)

        assert len(handler._errors) == 0
        assert len(handler._warnings) == 0


class TestLogMonitorHandlerThresholds:
    """Tests for threshold checking and alerting."""

    @pytest.fixture
    def handler(self):
        """Create handler with low thresholds for testing."""
        return LogMonitorHandler(
            window_seconds=300,
            error_threshold=3,
            warning_threshold=5,
        )

    def test_alerts_when_error_threshold_exceeded(self, handler):
        """Should create alert when error threshold exceeded."""
        with patch("tradingsystem.services.log_monitor.alert_service") as mock_alert:
            # Emit enough errors to exceed threshold
            for i in range(3):
                record = logging.LogRecord(
                    name="test",
                    level=logging.ERROR,
                    pathname="",
                    lineno=0,
                    msg=f"Error {i}",
                    args=(),
                    exc_info=None,
                )
                handler.emit(record)

            mock_alert.create_alert.assert_called_once()
            # Check that data dict contains error_count (4th positional arg)
            call_args = mock_alert.create_alert.call_args
            data = call_args[0][3] if len(call_args[0]) > 3 else call_args[1].get("data", {})
            assert "error_count" in data

    def test_alerts_only_once_for_sustained_errors(self, handler):
        """Should not alert repeatedly for sustained error rate."""
        with patch("tradingsystem.services.log_monitor.alert_service") as mock_alert:
            # Emit many errors
            for i in range(10):
                record = logging.LogRecord(
                    name="test",
                    level=logging.ERROR,
                    pathname="",
                    lineno=0,
                    msg=f"Error {i}",
                    args=(),
                    exc_info=None,
                )
                handler.emit(record)

            # Should only alert once
            assert mock_alert.create_alert.call_count == 1

    def test_alerts_when_warning_threshold_exceeded(self, handler):
        """Should create alert when warning threshold exceeded."""
        with patch("tradingsystem.services.log_monitor.alert_service") as mock_alert:
            # Emit enough warnings to exceed threshold
            for i in range(5):
                record = logging.LogRecord(
                    name="test",
                    level=logging.WARNING,
                    pathname="",
                    lineno=0,
                    msg=f"Warning {i}",
                    args=(),
                    exc_info=None,
                )
                handler.emit(record)

            mock_alert.create_alert.assert_called_once()

    def test_resets_alert_state_when_below_threshold(self, handler):
        """Should reset alert state when count drops below threshold."""
        with patch("tradingsystem.services.log_monitor.alert_service"):
            # Exceed threshold
            for i in range(3):
                record = logging.LogRecord(
                    name="test",
                    level=logging.ERROR,
                    pathname="",
                    lineno=0,
                    msg=f"Error {i}",
                    args=(),
                    exc_info=None,
                )
                handler.emit(record)

            assert handler._error_alert_active is True

            # Manually clear errors to simulate time passing
            handler._errors.clear()

            # Emit one more error (below threshold)
            record = logging.LogRecord(
                name="test",
                level=logging.ERROR,
                pathname="",
                lineno=0,
                msg="New error",
                args=(),
                exc_info=None,
            )
            handler.emit(record)

            # Alert state should still be True since we have 1 error (< 3 threshold)
            # It resets when we CHECK and find count < threshold
            # Actually checking _check_error_threshold logic:
            # if error_count >= threshold AND not active: alert
            # elif error_count < threshold AND active: reset
            # So with 1 error < 3 threshold and active=True, it should reset
            assert handler._error_alert_active is False


class TestLogMonitorHandlerPruning:
    """Tests for old entry pruning."""

    def test_prunes_old_errors(self):
        """Should prune errors outside the window."""
        handler = LogMonitorHandler(
            window_seconds=1,  # 1 second window
            error_threshold=100,
            warning_threshold=100,
        )

        # Add an error
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="Old error",
            args=(),
            exc_info=None,
        )
        handler.emit(record)

        assert len(handler._errors) == 1

        # Wait for window to pass
        time.sleep(1.1)

        # Emit another to trigger pruning
        handler.emit(record)

        # Old error should be pruned, only new one remains
        assert len(handler._errors) == 1

    def test_prunes_old_warnings(self):
        """Should prune warnings outside the window."""
        handler = LogMonitorHandler(
            window_seconds=1,
            error_threshold=100,
            warning_threshold=100,
        )

        # Add a warning
        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname="",
            lineno=0,
            msg="Old warning",
            args=(),
            exc_info=None,
        )
        handler.emit(record)

        assert len(handler._warnings) == 1

        # Wait for window to pass
        time.sleep(1.1)

        # Emit another to trigger pruning
        handler.emit(record)

        # Old warning should be pruned
        assert len(handler._warnings) == 1


class TestLogMonitorHandlerGetStats:
    """Tests for get_stats method."""

    def test_returns_log_stats(self):
        """Should return LogStats with current counts."""
        handler = LogMonitorHandler(
            window_seconds=300,
            error_threshold=10,
            warning_threshold=50,
        )

        # Add some logs
        for _ in range(3):
            handler.emit(logging.LogRecord(
                name="test", level=logging.ERROR, pathname="", lineno=0,
                msg="error", args=(), exc_info=None,
            ))
        for _ in range(5):
            handler.emit(logging.LogRecord(
                name="test", level=logging.WARNING, pathname="", lineno=0,
                msg="warning", args=(), exc_info=None,
            ))

        stats = handler.get_stats()

        assert isinstance(stats, LogStats)
        assert stats.error_count == 3
        assert stats.warning_count == 5
        assert stats.window_seconds == 300
        assert stats.error_threshold == 10
        assert stats.warning_threshold == 50

    def test_prunes_before_returning_stats(self):
        """Should prune old entries before returning stats."""
        handler = LogMonitorHandler(
            window_seconds=1,
            error_threshold=100,
            warning_threshold=100,
        )

        # Add an error
        handler.emit(logging.LogRecord(
            name="test", level=logging.ERROR, pathname="", lineno=0,
            msg="error", args=(), exc_info=None,
        ))

        # Wait for window to pass
        time.sleep(1.1)

        stats = handler.get_stats()

        # Error should be pruned
        assert stats.error_count == 0


class TestLogMonitorHandlerReset:
    """Tests for reset method."""

    def test_clears_all_counters(self):
        """Should clear all error and warning counts."""
        handler = LogMonitorHandler(
            window_seconds=300,
            error_threshold=10,
            warning_threshold=50,
        )

        # Add some logs
        for _ in range(5):
            handler.emit(logging.LogRecord(
                name="test", level=logging.ERROR, pathname="", lineno=0,
                msg="error", args=(), exc_info=None,
            ))
            handler.emit(logging.LogRecord(
                name="test", level=logging.WARNING, pathname="", lineno=0,
                msg="warning", args=(), exc_info=None,
            ))

        handler.reset()

        assert len(handler._errors) == 0
        assert len(handler._warnings) == 0

    def test_resets_alert_states(self):
        """Should reset alert active states."""
        handler = LogMonitorHandler(
            window_seconds=300,
            error_threshold=2,
            warning_threshold=2,
        )

        # Trigger alerts
        with patch("tradingsystem.services.log_monitor.alert_service"):
            for _ in range(3):
                handler.emit(logging.LogRecord(
                    name="test", level=logging.ERROR, pathname="", lineno=0,
                    msg="error", args=(), exc_info=None,
                ))
                handler.emit(logging.LogRecord(
                    name="test", level=logging.WARNING, pathname="", lineno=0,
                    msg="warning", args=(), exc_info=None,
                ))

        assert handler._error_alert_active is True
        assert handler._warning_alert_active is True

        handler.reset()

        assert handler._error_alert_active is False
        assert handler._warning_alert_active is False


# --- Module Functions Tests ---


class TestSetupLogMonitoring:
    """Tests for setup_log_monitoring function."""

    def test_creates_handler(self):
        """Should create and return handler."""
        import tradingsystem.services.log_monitor as log_monitor_module

        # Reset singleton
        log_monitor_module._log_monitor_handler = None

        with patch("tradingsystem.services.log_monitor.settings") as mock_settings:
            mock_settings.log_monitor_window_seconds = 300
            mock_settings.log_monitor_error_threshold = 10
            mock_settings.log_monitor_warning_threshold = 50

            handler = setup_log_monitoring()

            assert isinstance(handler, LogMonitorHandler)

        # Cleanup
        logging.getLogger().removeHandler(handler)
        log_monitor_module._log_monitor_handler = None

    def test_returns_same_instance_on_second_call(self):
        """Should return same instance on subsequent calls."""
        import tradingsystem.services.log_monitor as log_monitor_module

        # Reset singleton
        log_monitor_module._log_monitor_handler = None

        with patch("tradingsystem.services.log_monitor.settings") as mock_settings:
            mock_settings.log_monitor_window_seconds = 300
            mock_settings.log_monitor_error_threshold = 10
            mock_settings.log_monitor_warning_threshold = 50

            handler1 = setup_log_monitoring()
            handler2 = setup_log_monitoring()

            assert handler1 is handler2

        # Cleanup
        logging.getLogger().removeHandler(handler1)
        log_monitor_module._log_monitor_handler = None


class TestGetLogMonitor:
    """Tests for get_log_monitor function."""

    def test_returns_none_when_not_setup(self):
        """Should return None if not set up."""
        import tradingsystem.services.log_monitor as log_monitor_module

        original = log_monitor_module._log_monitor_handler
        log_monitor_module._log_monitor_handler = None

        result = get_log_monitor()

        assert result is None

        # Restore
        log_monitor_module._log_monitor_handler = original

    def test_returns_handler_when_setup(self):
        """Should return handler after setup."""
        import tradingsystem.services.log_monitor as log_monitor_module

        # Reset and setup
        log_monitor_module._log_monitor_handler = None

        with patch("tradingsystem.services.log_monitor.settings") as mock_settings:
            mock_settings.log_monitor_window_seconds = 300
            mock_settings.log_monitor_error_threshold = 10
            mock_settings.log_monitor_warning_threshold = 50

            setup_log_monitoring()
            result = get_log_monitor()

            assert isinstance(result, LogMonitorHandler)

        # Cleanup
        logging.getLogger().removeHandler(result)
        log_monitor_module._log_monitor_handler = None
