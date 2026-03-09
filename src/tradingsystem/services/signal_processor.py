"""Signal processor — evaluates strategies on bar close events.

When a bar closes on a Series, this processor:
1. Finds all Charts referencing that Series
2. For each Chart, finds enabled chart strategy assignments
3. Fetches candles, computes indicators, builds StrategyContext
4. Calls each strategy's generate_signals()
5. Saves signals to the database

Each strategy is evaluated independently — one failure does not block others.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any

from tradingsystem.core.database import get_cursor
from tradingsystem.models.signal import Signal
from tradingsystem.services import series_service, signal_service
from tradingsystem.services.bar_close_service import BarCloseEvent
from tradingsystem.services.order_pipeline import process_signals
from tradingsystem.strategies.base import StrategyContext
from tradingsystem.strategies.registry import StrategyRegistry

logger = logging.getLogger(__name__)


async def handle_bar_close(event: BarCloseEvent) -> dict[str, Any]:
    """Process a bar close event — evaluate all enabled strategies.

    Args:
        event: The bar close event with instrument, period, and bar time.

    Returns:
        Summary dict with signal counts per strategy and any errors.
    """
    instrument = event.instrument
    period = event.period

    logger.info(f"Processing bar close: {instrument} {period} at {event.bar_time}")

    # Find all charts on this series that have enabled strategies
    chart_strategies = await _get_enabled_chart_strategies(instrument, period)

    if not chart_strategies:
        logger.debug(f"No enabled strategies for {instrument} {period}")
        return {"instrument": instrument, "period": period, "strategies_evaluated": 0}

    # Fetch candles once for all strategies on this series
    df = await series_service.get_series_dataframe(
        instrument=instrument,
        period=period,
        limit=200,
    )

    if df.empty:
        logger.warning(f"No candle data for {instrument} {period}")
        return {
            "instrument": instrument,
            "period": period,
            "strategies_evaluated": 0,
            "error": "no_candle_data",
        }

    current_price = float(df["close"].iloc[-1])

    results: list[dict[str, Any]] = []
    total_signals = 0
    all_signals: list[Signal] = []

    for cs in chart_strategies:
        result = await _evaluate_strategy(
            cs=cs,
            instrument=instrument,
            period=period,
            df=df,
            current_price=current_price,
        )
        results.append(result)
        signal_count = result.get("signals", 0)
        total_signals += signal_count
        if signal_count > 0 and "_signal_objects" in result:
            all_signals.extend(result["_signal_objects"])

    # Route actionable signals through the order pipeline
    orders_placed = 0
    order_results = []
    if all_signals:
        order_results = await process_signals(all_signals)
        orders_placed = sum(1 for r in order_results if r.action == "order_placed")

    logger.info(
        f"Bar close complete: {instrument} {period} — "
        f"{len(chart_strategies)} strategies, {total_signals} signals, "
        f"{orders_placed} orders placed"
    )

    return {
        "instrument": instrument,
        "period": period,
        "bar_time": event.bar_time.isoformat(),
        "strategies_evaluated": len(chart_strategies),
        "total_signals": total_signals,
        "orders_placed": orders_placed,
        "results": results,
    }


async def _evaluate_strategy(
    cs: dict[str, Any],
    instrument: str,
    period: str,
    df: "pd.DataFrame",
    current_price: float,
) -> dict[str, Any]:
    """Evaluate a single chart strategy assignment.

    Isolated so one strategy failure doesn't affect others.
    """
    strategy_id = cs["strategy_id"]
    chart_strategy_id = str(cs["id"])
    params = cs.get("parameters") or {}
    start_time = time.monotonic()

    try:
        instance = StrategyRegistry.get_instance(strategy_id, **params)
        if not instance:
            logger.warning(f"Strategy not found in registry: {strategy_id}")
            return {
                "chart_strategy_id": chart_strategy_id,
                "strategy_id": strategy_id,
                "status": "error",
                "error": "strategy_not_found",
            }

        # Calculate required indicators
        from tradingsystem.services.strategy_service import _calculate_strategy_indicators

        indicators = await _calculate_strategy_indicators(instance, df)

        # Build context
        context = StrategyContext(
            instrument=instrument,
            period=period,
            candles=df,
            indicators=indicators,
            current_time=datetime.now(timezone.utc),
            current_price=current_price,
        )

        # Generate signals
        signals: list[Signal] = instance.generate_signals(context)

        # Save signals to database
        if signals:
            await signal_service.save_signals(signals)

        elapsed_ms = (time.monotonic() - start_time) * 1000

        logger.info(
            f"Strategy {strategy_id} on chart {cs['chart_id']}: "
            f"{len(signals)} signals in {elapsed_ms:.0f}ms"
        )

        result = {
            "chart_strategy_id": chart_strategy_id,
            "strategy_id": strategy_id,
            "status": "ok",
            "signals": len(signals),
            "elapsed_ms": round(elapsed_ms, 1),
        }
        if signals:
            result["_signal_objects"] = signals
        return result

    except Exception as e:
        elapsed_ms = (time.monotonic() - start_time) * 1000
        logger.error(
            f"Strategy {strategy_id} failed on {instrument} {period}: {e}",
            exc_info=True,
        )
        return {
            "chart_strategy_id": chart_strategy_id,
            "strategy_id": strategy_id,
            "status": "error",
            "error": str(e),
            "elapsed_ms": round(elapsed_ms, 1),
        }


async def _get_enabled_chart_strategies(
    instrument: str, period: str
) -> list[dict[str, Any]]:
    """Find all enabled chart strategies for a given instrument+period.

    Joins series → charts → chart_strategies to get enabled strategy
    assignments with their parameters.
    """
    async with get_cursor() as cur:
        await cur.execute(
            """
            SELECT cs.id, cs.chart_id, cs.strategy_id, cs.name, cs.parameters
            FROM chart_strategies cs
            JOIN charts c ON cs.chart_id = c.id
            JOIN series s ON c.series_id = s.id
            WHERE s.instrument = %s
              AND s.period = %s
              AND cs.enabled = true
            ORDER BY cs.created_at
            """,
            (instrument, period),
        )
        rows = await cur.fetchall()
        return [dict(row) for row in rows]
