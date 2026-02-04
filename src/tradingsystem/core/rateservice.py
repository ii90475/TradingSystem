"""HTTP client for RateService integration."""

import logging
from datetime import datetime
from decimal import Decimal

import httpx
from pydantic import BaseModel
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from tradingsystem.core.config import settings

logger = logging.getLogger(__name__)


class Candle(BaseModel):
    """OHLCV candle data from RateService."""

    time: datetime
    broker: str
    pair: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


class CurrentRate(BaseModel):
    """Current exchange rate from RateService."""

    pair: str
    bid: Decimal
    ask: Decimal
    time: datetime
    tradeable: bool = True


class RateServiceClient:
    """Async HTTP client for RateService API."""

    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or settings.rateservice_url

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        reraise=True,
    )
    async def get_current_rate(self, pair: str) -> CurrentRate:
        """Get current rate for a specific pair."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{self.base_url}/rates/current/{pair}")
            response.raise_for_status()
            return CurrentRate(**response.json())

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        reraise=True,
    )
    async def get_current_rates(self, pairs: list[str] | None = None) -> list[CurrentRate]:
        """Get current rates for multiple pairs."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            params = {}
            if pairs:
                params["pairs"] = pairs
            response = await client.get(f"{self.base_url}/rates/current", params=params)
            response.raise_for_status()
            return [CurrentRate(**rate) for rate in response.json()]

    # Map TradingSystem periods to RateService periods
    PERIOD_MAP = {
        "M1": "M1",      # Special case - uses /history endpoint
        "M5": "5m",
        "M15": "15m",
        "M30": "30m",
        "H1": "1h",
        "H4": "4h",
        "D": "1d",
        "D1": "1d",
        # Also accept lowercase formats
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "1h": "1h",
        "4h": "4h",
        "1d": "1d",
    }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        reraise=True,
    )
    async def get_candles(
        self,
        pair: str,
        period: str = "M1",
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
    ) -> list[Candle]:
        """
        Get historical candles from RateService.

        Args:
            pair: Currency pair (e.g., "EUR_USD")
            period: Candle period (M1, M5, M15, M30, H1, H4, D or lowercase equivalents)
            start: Start time for history
            end: End time for history
            limit: Maximum number of candles

        Returns:
            List of Candle objects
        """
        # Translate period to RateService format
        rs_period = self.PERIOD_MAP.get(period, period)

        async with httpx.AsyncClient(timeout=30.0) as client:
            params: dict = {"limit": limit}
            if start:
                params["start"] = start.isoformat()
            if end:
                params["end"] = end.isoformat()

            # Use the appropriate endpoint based on period
            if period == "M1":
                url = f"{self.base_url}/rates/{pair}/history"
            else:
                url = f"{self.base_url}/rates/{pair}/candles/{rs_period}"

            response = await client.get(url, params=params)
            response.raise_for_status()
            return [Candle(**candle) for candle in response.json()]

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        reraise=True,
    )
    async def get_pairs(self) -> list[str]:
        """Get list of available currency pairs."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{self.base_url}/rates/pairs")
            response.raise_for_status()
            return response.json()

    async def check_health(self) -> dict:
        """Check RateService health."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/health")
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "healthy": data.get("status") in ["healthy", "degraded"],
                        "status": data.get("status", "unknown"),
                        "error": None,
                    }
                return {
                    "healthy": False,
                    "status": "error",
                    "error": f"HTTP {response.status_code}",
                }
        except Exception as e:
            logger.error(f"RateService health check failed: {e}")
            return {
                "healthy": False,
                "status": "unreachable",
                "error": str(e),
            }


# Global client instance
rateservice_client = RateServiceClient()
