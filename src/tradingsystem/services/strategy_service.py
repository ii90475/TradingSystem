"""Strategy service for managing and executing trading strategies."""

import logging
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from tradingsystem.indicators import IndicatorRegistry, calculate_pandas_ta_indicator, ensure_initialized
from tradingsystem.models.signal import Signal
from tradingsystem.services import series_service, signal_service
from tradingsystem.strategies.base import BaseStrategy, StrategyContext
from tradingsystem.strategies.registry import StrategyRegistry, discover_builtin_strategies

logger = logging.getLogger(__name__)

# Track running strategies
_running_strategies: dict[str, dict[str, Any]] = {}


def initialize_strategies() -> int:
    """
    Initialize the strategy system.

    Discovers built-in strategies and registers them.

    Returns:
        Number of strategies discovered
    """
    ensure_initialized()  # Initialize indicators
    count = discover_builtin_strategies()
    logger.info(f"Initialized {count} built-in strategies")
    return count


def list_strategies() -> list[dict[str, Any]]:
    """List all available strategies with their info."""
    return StrategyRegistry.list_all()


def get_strategy_info(strategy_id: str) -> dict[str, Any] | None:
    """Get detailed info about a strategy."""
    strategy_cls = StrategyRegistry.get(strategy_id)
    if not strategy_cls:
        return None

    instance = strategy_cls()
    info = instance.get_info()
    info["id"] = strategy_id

    # Add running status
    if strategy_id in _running_strategies:
        info["is_running"] = True
        info["running_config"] = _running_strategies[strategy_id].get("config", {})
    else:
        info["is_running"] = False

    return info


def start_strategy(
    strategy_id: str,
    instruments: list[str] | None = None,
    periods: list[str] | None = None,
    **params: Any,
) -> dict[str, Any]:
    """
    Start a strategy for execution.

    Args:
        strategy_id: Strategy identifier
        instruments: Override default instruments
        periods: Override default periods
        **params: Strategy parameters

    Returns:
        Dict with start status and configuration
    """
    instance = StrategyRegistry.get_instance(strategy_id, **params)
    if not instance:
        raise ValueError(f"Strategy not found: {strategy_id}")

    # Validate strategy
    errors = instance.validate()
    if errors:
        raise ValueError(f"Strategy validation failed: {errors}")

    # Use provided or default instruments/periods
    active_instruments = instruments or instance.instruments
    active_periods = periods or instance.periods

    # Mark as running
    instance.on_start()

    _running_strategies[strategy_id] = {
        "instance": instance,
        "instruments": active_instruments,
        "periods": active_periods,
        "config": {
            "instruments": active_instruments,
            "periods": active_periods,
            "params": params,
        },
        "started_at": datetime.now(timezone.utc),
        "last_run": None,
        "signals_generated": 0,
    }

    logger.info(
        "strategy_started",
        extra={
            "event": "strategy",
            "action": "start",
            "strategy_id": strategy_id,
            "instruments": active_instruments,
            "periods": active_periods,
        },
    )

    return {
        "status": "started",
        "strategy_id": strategy_id,
        "instruments": active_instruments,
        "periods": active_periods,
        "params": params,
    }


def stop_strategy(strategy_id: str) -> dict[str, Any]:
    """
    Stop a running strategy.

    Args:
        strategy_id: Strategy identifier

    Returns:
        Dict with stop status and summary
    """
    if strategy_id not in _running_strategies:
        raise ValueError(f"Strategy not running: {strategy_id}")

    running_info = _running_strategies.pop(strategy_id)
    instance = running_info["instance"]
    instance.on_stop()

    logger.info(
        "strategy_stopped",
        extra={
            "event": "strategy",
            "action": "stop",
            "strategy_id": strategy_id,
            "signals_generated": running_info["signals_generated"],
        },
    )

    return {
        "status": "stopped",
        "strategy_id": strategy_id,
        "started_at": running_info["started_at"].isoformat(),
        "signals_generated": running_info["signals_generated"],
    }


def get_running_strategies() -> list[dict[str, Any]]:
    """Get list of currently running strategies."""
    result = []
    for strategy_id, info in _running_strategies.items():
        result.append({
            "strategy_id": strategy_id,
            "instruments": info["instruments"],
            "periods": info["periods"],
            "started_at": info["started_at"].isoformat(),
            "last_run": info["last_run"].isoformat() if info["last_run"] else None,
            "signals_generated": info["signals_generated"],
        })
    return result


def is_strategy_running(strategy_id: str) -> bool:
    """Check if a strategy is currently running."""
    return strategy_id in _running_strategies


async def run_strategy_once(
    strategy_id: str,
    instrument: str,
    period: str = "M1",
    limit: int = 100,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[Signal]:
    """
    Run a strategy once and return generated signals.

    This is useful for testing or manual execution.

    Args:
        strategy_id: Strategy identifier
        instrument: Currency pair
        period: Candle period
        limit: Number of candles to fetch
        start: Start time for candle data
        end: End time for candle data

    Returns:
        List of generated signals
    """
    instance = StrategyRegistry.get_instance(strategy_id)
    if not instance:
        raise ValueError(f"Strategy not found: {strategy_id}")

    # Fetch candle data
    df = await series_service.get_series_dataframe(
        instrument=instrument,
        period=period,
        limit=limit,
        start=start,
        end=end,
    )

    if df.empty:
        logger.warning(f"No candle data available for {instrument}/{period}")
        return []

    # Calculate required indicators
    indicators = await _calculate_strategy_indicators(instance, df)

    # Build context
    context = StrategyContext(
        instrument=instrument,
        period=period,
        candles=df,
        indicators=indicators,
        current_time=datetime.now(timezone.utc),
        current_price=float(df["close"].iloc[-1]),
    )

    # Generate signals
    signals = instance.generate_signals(context)

    # Save signals to database
    if signals:
        await signal_service.save_signals(signals)
        logger.info(f"Strategy {strategy_id} generated {len(signals)} signals for {instrument}")

    return signals


async def execute_running_strategies() -> dict[str, list[Signal]]:
    """
    Execute all running strategies.

    This is called by the scheduler on each tick.

    Returns:
        Dict mapping strategy_id to generated signals
    """
    all_signals: dict[str, list[Signal]] = {}

    for strategy_id, info in _running_strategies.items():
        instance: BaseStrategy = info["instance"]
        instruments = info["instruments"]
        periods = info["periods"]

        strategy_signals: list[Signal] = []

        for instrument in instruments:
            for period in periods:
                try:
                    signals = await _execute_strategy_for_pair(
                        instance=instance,
                        instrument=instrument,
                        period=period,
                    )
                    strategy_signals.extend(signals)
                except Exception as e:
                    logger.error(
                        f"Error executing {strategy_id} for {instrument}/{period}: {e}"
                    )

        # Update tracking
        info["last_run"] = datetime.now(timezone.utc)
        info["signals_generated"] += len(strategy_signals)

        if strategy_signals:
            all_signals[strategy_id] = strategy_signals

    return all_signals


async def _execute_strategy_for_pair(
    instance: BaseStrategy,
    instrument: str,
    period: str,
    limit: int = 100,
) -> list[Signal]:
    """Execute a strategy for a specific instrument/period pair."""
    # Fetch candle data
    df = await series_service.get_series_dataframe(
        instrument=instrument,
        period=period,
        limit=limit,
    )

    if df.empty:
        return []

    # Calculate indicators
    indicators = await _calculate_strategy_indicators(instance, df)

    # Build context
    context = StrategyContext(
        instrument=instrument,
        period=period,
        candles=df,
        indicators=indicators,
        current_time=datetime.now(timezone.utc),
        current_price=float(df["close"].iloc[-1]),
    )

    # Generate signals
    signals = instance.generate_signals(context)

    # Save signals
    if signals:
        await signal_service.save_signals(signals)

    return signals


async def _calculate_strategy_indicators(
    strategy: BaseStrategy,
    df: pd.DataFrame,
) -> dict[str, pd.Series | pd.DataFrame]:
    """Calculate all required indicators for a strategy."""
    indicators: dict[str, pd.Series | pd.DataFrame] = {}

    for config in strategy.required_indicators:
        try:
            # Try custom indicator first
            custom_cls = IndicatorRegistry.get(config.indicator_type)
            if custom_cls:
                instance = custom_cls()
                result = instance.calculate(df, **config.params)
            else:
                # Fall back to pandas-ta
                result = calculate_pandas_ta_indicator(
                    df,
                    config.indicator_type,
                    **config.params,
                )

            if result is not None:
                # Use custom column name or indicator type
                key = config.column_name or config.indicator_type
                indicators[key] = result

        except Exception as e:
            logger.warning(
                f"Failed to calculate indicator {config.indicator_type}: {e}"
            )

    return indicators
