"""Oanda Trading API client for live order execution."""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

import httpx
from pydantic import BaseModel
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from tradingsystem.core.config import settings

logger = logging.getLogger(__name__)


class OandaOrder(BaseModel):
    """Oanda order response."""

    id: str
    instrument: str
    units: Decimal
    price: Decimal | None = None
    state: str
    type: str
    time: datetime


class OandaTrade(BaseModel):
    """Oanda open trade."""

    id: str
    instrument: str
    units: Decimal
    price: Decimal
    unrealized_pnl: Decimal
    state: str
    open_time: datetime


class OandaAccount(BaseModel):
    """Oanda account summary."""

    id: str
    balance: Decimal
    nav: Decimal
    unrealized_pnl: Decimal
    margin_used: Decimal
    margin_available: Decimal
    open_trade_count: int
    open_position_count: int


class OandaOrderResponse(BaseModel):
    """Response from order creation."""

    order_id: str
    trade_id: str | None = None
    instrument: str
    units: Decimal
    price: Decimal
    time: datetime
    state: str


class OandaTradingClient:
    """Client for Oanda Trading API (v20)."""

    def __init__(self) -> None:
        self.base_url = settings.oanda_api_url
        self.account_id = settings.oanda_account_id
        self.headers = {
            "Authorization": f"Bearer {settings.oanda_api_key}",
            "Content-Type": "application/json",
        }
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=15.0)
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def _check_live_trading_enabled(self) -> None:
        """Raise error if live trading is not enabled."""
        if not settings.live_trading_enabled:
            raise RuntimeError(
                "Live trading is disabled. Set LIVE_TRADING_ENABLED=true to enable."
            )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        reraise=True,
    )
    async def get_account_summary(self) -> OandaAccount:
        """
        Get account summary including balance and margin.

        Returns:
            OandaAccount with current account state
        """
        client = await self._get_client()
        url = f"{self.base_url}/v3/accounts/{self.account_id}/summary"

        response = await client.get(url, headers=self.headers)
        response.raise_for_status()
        data = response.json()

        account = data["account"]
        return OandaAccount(
            id=account["id"],
            balance=Decimal(account["balance"]),
            nav=Decimal(account["NAV"]),
            unrealized_pnl=Decimal(account["unrealizedPL"]),
            margin_used=Decimal(account["marginUsed"]),
            margin_available=Decimal(account["marginAvailable"]),
            open_trade_count=account["openTradeCount"],
            open_position_count=account["openPositionCount"],
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        reraise=True,
    )
    async def get_open_trades(self) -> list[OandaTrade]:
        """
        Get all open trades.

        Returns:
            List of open OandaTrade objects
        """
        client = await self._get_client()
        url = f"{self.base_url}/v3/accounts/{self.account_id}/openTrades"

        response = await client.get(url, headers=self.headers)
        response.raise_for_status()
        data = response.json()

        trades = []
        for trade in data.get("trades", []):
            trades.append(
                OandaTrade(
                    id=trade["id"],
                    instrument=trade["instrument"],
                    units=Decimal(trade["currentUnits"]),
                    price=Decimal(trade["price"]),
                    unrealized_pnl=Decimal(trade["unrealizedPL"]),
                    state=trade["state"],
                    open_time=datetime.fromisoformat(
                        trade["openTime"].replace("Z", "+00:00")
                    ),
                )
            )
        return trades

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        reraise=True,
    )
    async def create_market_order(
        self,
        instrument: str,
        units: Decimal,
        stop_loss: Decimal | None = None,
        take_profit: Decimal | None = None,
    ) -> OandaOrderResponse:
        """
        Create a market order.

        Args:
            instrument: Currency pair (e.g., "EUR_USD")
            units: Positive for buy, negative for sell
            stop_loss: Optional stop loss price
            take_profit: Optional take profit price

        Returns:
            OandaOrderResponse with fill details
        """
        self._check_live_trading_enabled()

        client = await self._get_client()
        url = f"{self.base_url}/v3/accounts/{self.account_id}/orders"

        order_data: dict[str, Any] = {
            "order": {
                "type": "MARKET",
                "instrument": instrument,
                "units": str(units),
                "timeInForce": "FOK",  # Fill or Kill
                "positionFill": "DEFAULT",
            }
        }

        if stop_loss:
            order_data["order"]["stopLossOnFill"] = {"price": str(stop_loss)}
        if take_profit:
            order_data["order"]["takeProfitOnFill"] = {"price": str(take_profit)}

        logger.info(
            "creating_market_order",
            extra={
                "instrument": instrument,
                "units": str(units),
                "stop_loss": str(stop_loss) if stop_loss else None,
                "take_profit": str(take_profit) if take_profit else None,
            },
        )

        response = await client.post(url, headers=self.headers, json=order_data)
        response.raise_for_status()
        data = response.json()

        # Handle filled order
        if "orderFillTransaction" in data:
            fill = data["orderFillTransaction"]
            return OandaOrderResponse(
                order_id=fill["orderID"],
                trade_id=fill.get("tradeOpened", {}).get("tradeID"),
                instrument=fill["instrument"],
                units=Decimal(fill["units"]),
                price=Decimal(fill["price"]),
                time=datetime.fromisoformat(fill["time"].replace("Z", "+00:00")),
                state="FILLED",
            )

        # Handle rejected order
        if "orderRejectTransaction" in data:
            reject = data["orderRejectTransaction"]
            raise RuntimeError(f"Order rejected: {reject.get('rejectReason', 'Unknown')}")

        # Handle cancelled order
        if "orderCancelTransaction" in data:
            cancel = data["orderCancelTransaction"]
            raise RuntimeError(f"Order cancelled: {cancel.get('reason', 'Unknown')}")

        raise RuntimeError(f"Unexpected order response: {data}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        reraise=True,
    )
    async def create_limit_order(
        self,
        instrument: str,
        units: Decimal,
        price: Decimal,
        stop_loss: Decimal | None = None,
        take_profit: Decimal | None = None,
    ) -> OandaOrderResponse:
        """
        Create a limit order.

        Args:
            instrument: Currency pair
            units: Positive for buy, negative for sell
            price: Limit price
            stop_loss: Optional stop loss price
            take_profit: Optional take profit price

        Returns:
            OandaOrderResponse with order details
        """
        self._check_live_trading_enabled()

        client = await self._get_client()
        url = f"{self.base_url}/v3/accounts/{self.account_id}/orders"

        order_data: dict[str, Any] = {
            "order": {
                "type": "LIMIT",
                "instrument": instrument,
                "units": str(units),
                "price": str(price),
                "timeInForce": "GTC",  # Good Till Cancelled
                "positionFill": "DEFAULT",
            }
        }

        if stop_loss:
            order_data["order"]["stopLossOnFill"] = {"price": str(stop_loss)}
        if take_profit:
            order_data["order"]["takeProfitOnFill"] = {"price": str(take_profit)}

        logger.info(
            "creating_limit_order",
            extra={
                "instrument": instrument,
                "units": str(units),
                "price": str(price),
            },
        )

        response = await client.post(url, headers=self.headers, json=order_data)
        response.raise_for_status()
        data = response.json()

        if "orderCreateTransaction" in data:
            order = data["orderCreateTransaction"]
            return OandaOrderResponse(
                order_id=order["id"],
                trade_id=None,
                instrument=order["instrument"],
                units=Decimal(order["units"]),
                price=Decimal(order["price"]),
                time=datetime.fromisoformat(order["time"].replace("Z", "+00:00")),
                state="PENDING",
            )

        if "orderRejectTransaction" in data:
            reject = data["orderRejectTransaction"]
            raise RuntimeError(f"Order rejected: {reject.get('rejectReason', 'Unknown')}")

        raise RuntimeError(f"Unexpected order response: {data}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        reraise=True,
    )
    async def close_trade(self, trade_id: str, units: Decimal | None = None) -> OandaOrderResponse:
        """
        Close an open trade.

        Args:
            trade_id: Oanda trade ID
            units: Optional partial close (None = close all)

        Returns:
            OandaOrderResponse with close details
        """
        self._check_live_trading_enabled()

        client = await self._get_client()
        url = f"{self.base_url}/v3/accounts/{self.account_id}/trades/{trade_id}/close"

        body = {}
        if units:
            body["units"] = str(units)

        logger.info(
            "closing_trade",
            extra={"trade_id": trade_id, "units": str(units) if units else "ALL"},
        )

        response = await client.put(url, headers=self.headers, json=body)
        response.raise_for_status()
        data = response.json()

        if "orderFillTransaction" in data:
            fill = data["orderFillTransaction"]
            return OandaOrderResponse(
                order_id=fill["orderID"],
                trade_id=trade_id,
                instrument=fill["instrument"],
                units=Decimal(fill["units"]),
                price=Decimal(fill["price"]),
                time=datetime.fromisoformat(fill["time"].replace("Z", "+00:00")),
                state="FILLED",
            )

        raise RuntimeError(f"Unexpected close response: {data}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        reraise=True,
    )
    async def cancel_order(self, order_id: str) -> dict:
        """
        Cancel a pending order.

        Args:
            order_id: Oanda order ID

        Returns:
            Cancellation response
        """
        self._check_live_trading_enabled()

        client = await self._get_client()
        url = f"{self.base_url}/v3/accounts/{self.account_id}/orders/{order_id}/cancel"

        response = await client.put(url, headers=self.headers)
        response.raise_for_status()
        return response.json()

    async def get_pending_orders(self) -> list[OandaOrder]:
        """
        Get all pending orders.

        Returns:
            List of pending OandaOrder objects
        """
        client = await self._get_client()
        url = f"{self.base_url}/v3/accounts/{self.account_id}/pendingOrders"

        response = await client.get(url, headers=self.headers)
        response.raise_for_status()
        data = response.json()

        orders = []
        for order in data.get("orders", []):
            orders.append(
                OandaOrder(
                    id=order["id"],
                    instrument=order["instrument"],
                    units=Decimal(order["units"]),
                    price=Decimal(order.get("price", "0")),
                    state=order["state"],
                    type=order["type"],
                    time=datetime.fromisoformat(order["createTime"].replace("Z", "+00:00")),
                )
            )
        return orders

    async def close_all_trades(self) -> list[OandaOrderResponse]:
        """
        Emergency: Close all open trades.

        Returns:
            List of close responses
        """
        self._check_live_trading_enabled()

        trades = await self.get_open_trades()
        results = []

        for trade in trades:
            try:
                result = await self.close_trade(trade.id)
                results.append(result)
                logger.warning(f"Emergency closed trade {trade.id}")
            except Exception as e:
                logger.error(f"Failed to close trade {trade.id}: {e}")

        return results

    async def check_connectivity(self) -> dict:
        """
        Check API connectivity and authentication.

        Returns:
            Dict with connectivity status
        """
        try:
            account = await self.get_account_summary()
            return {
                "connected": True,
                "account_id": account.id,
                "balance": str(account.balance),
                "live_trading_enabled": settings.live_trading_enabled,
            }
        except Exception as e:
            return {
                "connected": False,
                "error": str(e),
                "live_trading_enabled": settings.live_trading_enabled,
            }


# Singleton instance
oanda_trading_client = OandaTradingClient()
