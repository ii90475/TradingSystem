"""Twilio SMS alert handler for critical notifications."""

import logging

from tradingsystem.core.config import settings
from tradingsystem.services.alert_service import Alert, AlertLevel

logger = logging.getLogger(__name__)


class TwilioSMSHandler:
    """
    Alert handler that sends SMS notifications via Twilio.

    Gracefully disabled if credentials are not configured.
    Only sends SMS for CRITICAL alerts by default (WARNING optional via config).
    """

    def __init__(self) -> None:
        self._client = None
        self._enabled = False

        # Check if credentials are configured
        if not all([
            settings.twilio_account_sid,
            settings.twilio_auth_token,
            settings.twilio_from_number,
            settings.twilio_to_number,
        ]):
            logger.info("Twilio SMS disabled: credentials not configured")
            return

        try:
            from twilio.rest import Client

            self._client = Client(
                settings.twilio_account_sid,
                settings.twilio_auth_token,
            )
            self._enabled = True
            logger.info("Twilio SMS handler initialized")
        except ImportError:
            logger.warning("Twilio SMS disabled: twilio package not installed")
        except Exception as e:
            logger.error(f"Twilio SMS initialization failed: {e}")

    @property
    def enabled(self) -> bool:
        """Check if SMS sending is enabled."""
        return self._enabled

    def __call__(self, alert: Alert) -> None:
        """
        Handle an alert by sending SMS if appropriate.

        Args:
            alert: The alert to handle
        """
        if not self._enabled:
            return

        # Only send SMS for CRITICAL alerts (and optionally WARNING)
        should_send = alert.level == AlertLevel.CRITICAL
        if settings.twilio_alert_on_warning and alert.level == AlertLevel.WARNING:
            should_send = True

        if not should_send:
            return

        self._send_sms(alert)

    def _send_sms(self, alert: Alert) -> None:
        """Send SMS for an alert."""
        try:
            # Format message for SMS (keep under 160 chars for single segment)
            message_body = f"[{alert.level.value}] {alert.type.value}: {alert.message}"
            if len(message_body) > 160:
                message_body = message_body[:157] + "..."

            self._client.messages.create(
                body=message_body,
                from_=settings.twilio_from_number,
                to=settings.twilio_to_number,
            )

            logger.info(
                f"SMS sent for alert {alert.id}",
                extra={"alert_id": alert.id, "alert_type": alert.type.value},
            )
        except Exception as e:
            logger.error(f"Failed to send SMS for alert {alert.id}: {e}")

    def send_test_message(self) -> bool:
        """
        Send a test SMS message.

        Returns:
            True if successful, False otherwise
        """
        if not self._enabled:
            return False

        try:
            self._client.messages.create(
                body="TradingSystem: Test message - SMS alerts are working",
                from_=settings.twilio_from_number,
                to=settings.twilio_to_number,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send test SMS: {e}")
            return False


# Singleton instance
twilio_handler = TwilioSMSHandler()
