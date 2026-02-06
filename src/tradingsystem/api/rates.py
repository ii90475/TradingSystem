"""Real-time rates API endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from tradingsystem.core.rateservice import rateservice_client

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
