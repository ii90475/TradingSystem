"""Application configuration using pydantic-settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_name: str = "TradingSystem"
    debug: bool = False

    # Database (same TimescaleDB as RateService)
    database_url: str = "postgresql://localhost:5432/rateservice"

    # RateService integration
    rateservice_url: str = "http://localhost:8000"

    # Oanda API (for live trading)
    oanda_api_key: str = ""
    oanda_account_id: str = ""
    oanda_api_url: str = "https://api-fxtrade.oanda.com"

    # Trading parameters
    paper_trading_enabled: bool = True
    live_trading_enabled: bool = False

    # Risk management
    max_position_size_pct: float = 5.0
    max_daily_loss_pct: float = 2.0
    max_open_positions: int = 5

    # Default instruments to track
    default_instruments: list[str] = [
        "EUR_USD",
        "GBP_USD",
        "USD_JPY",
    ]


settings = Settings()
