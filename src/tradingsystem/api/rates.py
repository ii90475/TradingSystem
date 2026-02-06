"""Real-time rates API endpoints."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from tradingsystem.core.config import settings
from tradingsystem.core.rateservice import rateservice_client
from tradingsystem.core.websocket_manager import rate_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rates", tags=["rates"])


class CurrentRateResponse(BaseModel):
    """Current rate response with freshness info."""

    pair: str
    bid: str
    ask: str
    mid: str
    spread: str
    time: datetime
    age_seconds: float
    tradeable: bool


@router.get("/current/{pair}", response_model=CurrentRateResponse)
async def get_current_rate(pair: str) -> CurrentRateResponse:
    """
    Get real-time current rate for a currency pair.

    This endpoint provides sub-second fresh pricing data directly
    from RateService, which streams from OANDA.

    Args:
        pair: Currency pair (e.g., EUR_USD)

    Returns:
        Current bid/ask/mid prices with freshness metadata
    """
    try:
        rate = await rateservice_client.get_current_rate(pair)

        now = datetime.now(timezone.utc)
        age_seconds = (now - rate.time.replace(tzinfo=timezone.utc)).total_seconds()

        bid = float(rate.bid)
        ask = float(rate.ask)
        mid = (bid + ask) / 2
        spread = ask - bid

        return CurrentRateResponse(
            pair=rate.pair,
            bid=f"{bid:.5f}",
            ask=f"{ask:.5f}",
            mid=f"{mid:.5f}",
            spread=f"{spread:.5f}",
            time=rate.time,
            age_seconds=round(age_seconds, 1),
            tradeable=rate.tradeable,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to get rate for {pair}: {e}")


@router.get("/current", response_model=list[CurrentRateResponse])
async def get_current_rates(
    pairs: list[str] = Query(None, description="Currency pairs to fetch"),
) -> list[CurrentRateResponse]:
    """
    Get real-time current rates for multiple currency pairs.

    If no pairs specified, returns all available pairs.

    Returns:
        List of current rates with freshness metadata
    """
    try:
        rates = await rateservice_client.get_current_rates(pairs)
        now = datetime.now(timezone.utc)

        result = []
        for rate in rates:
            age_seconds = (now - rate.time.replace(tzinfo=timezone.utc)).total_seconds()
            bid = float(rate.bid)
            ask = float(rate.ask)
            mid = (bid + ask) / 2
            spread = ask - bid

            result.append(
                CurrentRateResponse(
                    pair=rate.pair,
                    bid=f"{bid:.5f}",
                    ask=f"{ask:.5f}",
                    mid=f"{mid:.5f}",
                    spread=f"{spread:.5f}",
                    time=rate.time,
                    age_seconds=round(age_seconds, 1),
                    tradeable=rate.tradeable,
                )
            )

        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to get rates: {e}")


@router.get("/pairs", response_model=list[str])
async def get_available_pairs() -> list[str]:
    """Get list of available currency pairs from RateService."""
    try:
        return await rateservice_client.get_pairs()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to get pairs: {e}")


@router.websocket("/ws")
async def rates_websocket(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for real-time rate streaming.

    Connects to receive continuous rate updates at the configured
    polling interval (default 250ms). Messages are JSON with format:

    {
        "type": "rates",
        "timestamp": "2024-01-15T10:30:00Z",
        "data": [
            {"pair": "EUR_USD", "bid": "1.08500", "ask": "1.08520", ...},
            ...
        ]
    }

    Error messages have format:
    {
        "type": "error",
        "message": "Error description",
        "timestamp": "2024-01-15T10:30:00Z"
    }
    """
    if not settings.ws_enabled:
        await websocket.close(code=1008, reason="WebSocket disabled")
        return

    await rate_manager.connect(websocket)
    try:
        # Keep connection alive, listening for client messages
        while True:
            # Wait for any message from client (ping/pong or commands)
            data = await websocket.receive_text()
            # Could handle client commands here (e.g., subscribe to specific pairs)
            logger.debug(f"WebSocket received: {data}")
    except WebSocketDisconnect:
        rate_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        rate_manager.disconnect(websocket)


@router.get("/ws/status")
async def get_websocket_status() -> dict:
    """Get WebSocket streaming status."""
    return {
        "enabled": settings.ws_enabled,
        "poll_interval_ms": settings.ws_rate_poll_interval_ms,
        "active_connections": rate_manager.connection_count,
        "broadcaster_running": rate_manager.is_running,
    }
