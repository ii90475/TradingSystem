"""Tests for application configuration."""

from unittest.mock import patch
import os

import pytest

from tradingsystem.core.config import Settings


class TestSettingsDefaults:
    """Tests for Settings default values."""

    def test_app_name_default(self):
        """Should have default app name."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(_env_file=None)
            assert settings.app_name == "TradingSystem"

    def test_debug_default_false(self):
        """Should default debug to False."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(_env_file=None)
            assert settings.debug is False

    def test_database_url_default(self):
        """Should have default database URL."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(_env_file=None)
            assert "postgresql" in settings.database_url

    def test_rateservice_url_default(self):
        """Should have default RateService URL."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(_env_file=None)
            assert settings.rateservice_url == "http://localhost:8000"

    def test_paper_trading_enabled_default(self):
        """Should enable paper trading by default."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(_env_file=None)
            assert settings.paper_trading_enabled is True

    def test_live_trading_disabled_default(self):
        """Should disable live trading by default."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(_env_file=None)
            assert settings.live_trading_enabled is False


class TestSettingsEnvironmentOverride:
    """Tests for Settings environment variable loading."""

    def test_database_url_from_env(self):
        """Should load database URL from environment."""
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://custom/db"}, clear=True):
            settings = Settings(_env_file=None)
            assert settings.database_url == "postgresql://custom/db"

    def test_live_trading_enabled_from_env(self):
        """Should enable live trading from environment."""
        with patch.dict(os.environ, {"LIVE_TRADING_ENABLED": "true"}, clear=True):
            settings = Settings(_env_file=None)
            assert settings.live_trading_enabled is True

    def test_oanda_credentials_from_env(self):
        """Should load OANDA credentials from environment."""
        env = {
            "OANDA_API_KEY": "test-key-123",
            "OANDA_ACCOUNT_ID": "001-001-12345",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = Settings(_env_file=None)
            assert settings.oanda_api_key == "test-key-123"
            assert settings.oanda_account_id == "001-001-12345"


class TestSettingsRiskParameters:
    """Tests for risk management settings."""

    def test_max_position_size_default(self):
        """Should have default max position size."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(_env_file=None)
            assert settings.max_position_size_pct == 5.0

    def test_max_daily_loss_default(self):
        """Should have default max daily loss."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(_env_file=None)
            assert settings.max_daily_loss_pct == 2.0

    def test_max_open_positions_default(self):
        """Should have default max open positions."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(_env_file=None)
            assert settings.max_open_positions == 5

    def test_risk_params_from_env(self):
        """Should load risk parameters from environment."""
        env = {
            "MAX_POSITION_SIZE_PCT": "10.0",
            "MAX_DAILY_LOSS_PCT": "3.0",
            "MAX_OPEN_POSITIONS": "10",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = Settings(_env_file=None)
            assert settings.max_position_size_pct == 10.0
            assert settings.max_daily_loss_pct == 3.0
            assert settings.max_open_positions == 10


class TestSettingsMonitoring:
    """Tests for monitoring settings."""

    def test_monitoring_enabled_default(self):
        """Should enable monitoring by default."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(_env_file=None)
            assert settings.monitoring_enabled is True

    def test_monitoring_interval_default(self):
        """Should have default monitoring interval."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(_env_file=None)
            assert settings.monitoring_interval_minutes == 1


class TestSettingsDefaultInstruments:
    """Tests for default instruments configuration."""

    def test_default_instruments_list(self):
        """Should have default instruments list."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(_env_file=None)
            assert "EUR_USD" in settings.default_instruments
            assert "GBP_USD" in settings.default_instruments
            assert "USD_JPY" in settings.default_instruments
