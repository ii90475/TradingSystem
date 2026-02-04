"""Tests for Twilio SMS handler."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from tradingsystem.services.alert_service import AlertLevel, AlertType


# --- TwilioSMSHandler Tests ---


class TestTwilioSMSHandlerInit:
    """Tests for TwilioSMSHandler initialization."""

    def test_disabled_when_no_credentials(self):
        """Should be disabled when credentials not configured."""
        with patch("tradingsystem.services.twilio_handler.settings") as mock_settings:
            mock_settings.twilio_account_sid = None
            mock_settings.twilio_auth_token = None
            mock_settings.twilio_from_number = None
            mock_settings.twilio_to_number = None

            # Import fresh to test init
            from tradingsystem.services.twilio_handler import TwilioSMSHandler
            handler = TwilioSMSHandler()

            assert handler.enabled is False
            assert handler._client is None

    def test_disabled_when_partial_credentials(self):
        """Should be disabled when only some credentials configured."""
        with patch("tradingsystem.services.twilio_handler.settings") as mock_settings:
            mock_settings.twilio_account_sid = "AC12345"
            mock_settings.twilio_auth_token = "token123"
            mock_settings.twilio_from_number = None  # Missing
            mock_settings.twilio_to_number = "+1234567890"

            from tradingsystem.services.twilio_handler import TwilioSMSHandler
            handler = TwilioSMSHandler()

            assert handler.enabled is False

    def test_disabled_when_twilio_import_fails(self):
        """Should be disabled when twilio package not installed."""
        with patch("tradingsystem.services.twilio_handler.settings") as mock_settings:
            mock_settings.twilio_account_sid = "AC12345"
            mock_settings.twilio_auth_token = "token123"
            mock_settings.twilio_from_number = "+1111111111"
            mock_settings.twilio_to_number = "+2222222222"

            # Mock import to raise ImportError
            with patch.dict("sys.modules", {"twilio": None, "twilio.rest": None}):
                from tradingsystem.services.twilio_handler import TwilioSMSHandler

                # Create handler where import will fail
                with patch("builtins.__import__", side_effect=ImportError("No module named twilio")):
                    handler = TwilioSMSHandler()

                    assert handler.enabled is False

    def test_enabled_when_properly_configured(self):
        """Should be enabled when fully configured."""
        mock_client = MagicMock()

        with patch("tradingsystem.services.twilio_handler.settings") as mock_settings:
            mock_settings.twilio_account_sid = "AC12345"
            mock_settings.twilio_auth_token = "token123"
            mock_settings.twilio_from_number = "+1111111111"
            mock_settings.twilio_to_number = "+2222222222"

            with patch.dict("sys.modules", {"twilio": MagicMock(), "twilio.rest": MagicMock()}):
                # Mock the Client import
                mock_twilio_rest = MagicMock()
                mock_twilio_rest.Client.return_value = mock_client

                with patch("tradingsystem.services.twilio_handler.TwilioSMSHandler.__init__", return_value=None):
                    from tradingsystem.services.twilio_handler import TwilioSMSHandler
                    handler = TwilioSMSHandler()
                    handler._client = mock_client
                    handler._enabled = True

                    assert handler.enabled is True


class TestTwilioSMSHandlerEnabled:
    """Tests for enabled property."""

    def test_returns_enabled_state(self):
        """Should return internal enabled state."""
        with patch("tradingsystem.services.twilio_handler.settings") as mock_settings:
            mock_settings.twilio_account_sid = None
            mock_settings.twilio_auth_token = None
            mock_settings.twilio_from_number = None
            mock_settings.twilio_to_number = None

            from tradingsystem.services.twilio_handler import TwilioSMSHandler
            handler = TwilioSMSHandler()

            assert handler.enabled is False

            # Manually enable
            handler._enabled = True
            assert handler.enabled is True


class TestTwilioSMSHandlerCall:
    """Tests for __call__ method (alert handling)."""

    def _create_handler(self):
        """Create enabled handler with mock client."""
        from tradingsystem.services.twilio_handler import TwilioSMSHandler
        handler = TwilioSMSHandler.__new__(TwilioSMSHandler)
        handler._enabled = True
        handler._client = MagicMock()
        return handler

    def _create_alert(self, level=AlertLevel.CRITICAL):
        """Create mock alert."""
        alert = MagicMock()
        alert.id = uuid4()
        alert.type = AlertType.POSITION_SIZE
        alert.level = level
        alert.message = "Test alert message"
        return alert

    def test_skips_when_disabled(self):
        """Should not send SMS when disabled."""
        from tradingsystem.services.twilio_handler import TwilioSMSHandler
        handler = TwilioSMSHandler.__new__(TwilioSMSHandler)
        handler._enabled = False
        handler._client = None
        handler._send_sms = MagicMock()

        alert = self._create_alert()
        handler(alert)

        handler._send_sms.assert_not_called()

    def test_sends_for_critical_alert(self):
        """Should send SMS for CRITICAL alert."""
        handler = self._create_handler()
        handler._send_sms = MagicMock()
        alert = self._create_alert(AlertLevel.CRITICAL)

        with patch("tradingsystem.services.twilio_handler.settings") as mock_settings:
            mock_settings.twilio_alert_on_warning = False

            handler(alert)

            handler._send_sms.assert_called_once_with(alert)

    def test_skips_info_level(self):
        """Should not send SMS for INFO level."""
        handler = self._create_handler()
        handler._send_sms = MagicMock()
        alert = self._create_alert(AlertLevel.INFO)

        with patch("tradingsystem.services.twilio_handler.settings") as mock_settings:
            mock_settings.twilio_alert_on_warning = False

            handler(alert)

            handler._send_sms.assert_not_called()

    def test_skips_warning_by_default(self):
        """Should not send SMS for WARNING by default."""
        handler = self._create_handler()
        handler._send_sms = MagicMock()
        alert = self._create_alert(AlertLevel.WARNING)

        with patch("tradingsystem.services.twilio_handler.settings") as mock_settings:
            mock_settings.twilio_alert_on_warning = False

            handler(alert)

            handler._send_sms.assert_not_called()

    def test_sends_warning_when_configured(self):
        """Should send SMS for WARNING when configured."""
        handler = self._create_handler()
        handler._send_sms = MagicMock()
        alert = self._create_alert(AlertLevel.WARNING)

        with patch("tradingsystem.services.twilio_handler.settings") as mock_settings:
            mock_settings.twilio_alert_on_warning = True

            handler(alert)

            handler._send_sms.assert_called_once_with(alert)


class TestTwilioSMSHandlerSendSMS:
    """Tests for _send_sms method."""

    def _create_handler(self):
        """Create enabled handler with mock client."""
        from tradingsystem.services.twilio_handler import TwilioSMSHandler
        handler = TwilioSMSHandler.__new__(TwilioSMSHandler)
        handler._enabled = True
        handler._client = MagicMock()
        return handler

    def _create_alert(self, message="Test message"):
        """Create mock alert."""
        alert = MagicMock()
        alert.id = uuid4()
        alert.type = AlertType.POSITION_SIZE
        alert.level = AlertLevel.CRITICAL
        alert.message = message
        return alert

    def test_sends_message_via_client(self):
        """Should send SMS via Twilio client."""
        handler = self._create_handler()
        alert = self._create_alert()

        with patch("tradingsystem.services.twilio_handler.settings") as mock_settings:
            mock_settings.twilio_from_number = "+1111111111"
            mock_settings.twilio_to_number = "+2222222222"

            handler._send_sms(alert)

            handler._client.messages.create.assert_called_once()

    def test_formats_message_correctly(self):
        """Should format message with level and type."""
        handler = self._create_handler()
        alert = self._create_alert("Test message")

        with patch("tradingsystem.services.twilio_handler.settings") as mock_settings:
            mock_settings.twilio_from_number = "+1111111111"
            mock_settings.twilio_to_number = "+2222222222"

            handler._send_sms(alert)

            call_kwargs = handler._client.messages.create.call_args[1]
            assert "CRITICAL" in call_kwargs["body"]
            assert "POSITION_SIZE" in call_kwargs["body"]
            assert "Test message" in call_kwargs["body"]

    def test_truncates_long_message(self):
        """Should truncate message to 160 chars."""
        handler = self._create_handler()
        alert = self._create_alert("A" * 200)

        with patch("tradingsystem.services.twilio_handler.settings") as mock_settings:
            mock_settings.twilio_from_number = "+1111111111"
            mock_settings.twilio_to_number = "+2222222222"

            handler._send_sms(alert)

            call_kwargs = handler._client.messages.create.call_args[1]
            assert len(call_kwargs["body"]) <= 160
            assert call_kwargs["body"].endswith("...")

    def test_handles_send_failure(self):
        """Should handle SMS send failure gracefully."""
        handler = self._create_handler()
        handler._client.messages.create.side_effect = Exception("Network error")
        alert = self._create_alert()

        with patch("tradingsystem.services.twilio_handler.settings") as mock_settings:
            mock_settings.twilio_from_number = "+1111111111"
            mock_settings.twilio_to_number = "+2222222222"

            # Should not raise
            handler._send_sms(alert)


class TestTwilioSMSHandlerSendTestMessage:
    """Tests for send_test_message method."""

    def test_returns_false_when_disabled(self):
        """Should return False when disabled."""
        with patch("tradingsystem.services.twilio_handler.settings") as mock_settings:
            mock_settings.twilio_account_sid = None
            mock_settings.twilio_auth_token = None
            mock_settings.twilio_from_number = None
            mock_settings.twilio_to_number = None

            from tradingsystem.services.twilio_handler import TwilioSMSHandler
            handler = TwilioSMSHandler()

            result = handler.send_test_message()

            assert result is False

    def test_returns_true_on_success(self):
        """Should return True when test message sent."""
        with patch("tradingsystem.services.twilio_handler.settings") as mock_settings:
            mock_settings.twilio_from_number = "+1111111111"
            mock_settings.twilio_to_number = "+2222222222"

            from tradingsystem.services.twilio_handler import TwilioSMSHandler
            handler = TwilioSMSHandler()
            handler._enabled = True
            handler._client = MagicMock()

            result = handler.send_test_message()

            assert result is True
            handler._client.messages.create.assert_called_once()

    def test_sends_correct_test_message(self):
        """Should send correct test message body."""
        with patch("tradingsystem.services.twilio_handler.settings") as mock_settings:
            mock_settings.twilio_from_number = "+1111111111"
            mock_settings.twilio_to_number = "+2222222222"

            from tradingsystem.services.twilio_handler import TwilioSMSHandler
            handler = TwilioSMSHandler()
            handler._enabled = True
            handler._client = MagicMock()

            handler.send_test_message()

            call_kwargs = handler._client.messages.create.call_args[1]
            assert "TradingSystem" in call_kwargs["body"]
            assert "Test message" in call_kwargs["body"]

    def test_returns_false_on_failure(self):
        """Should return False when send fails."""
        with patch("tradingsystem.services.twilio_handler.settings") as mock_settings:
            mock_settings.twilio_from_number = "+1111111111"
            mock_settings.twilio_to_number = "+2222222222"

            from tradingsystem.services.twilio_handler import TwilioSMSHandler
            handler = TwilioSMSHandler()
            handler._enabled = True
            handler._client = MagicMock()
            handler._client.messages.create.side_effect = Exception("Failed")

            result = handler.send_test_message()

            assert result is False
