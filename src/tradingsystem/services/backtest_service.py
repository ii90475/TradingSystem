"""Backtest service for running and managing backtests."""

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from tradingsystem.backtest.engine import BacktestEngine
from tradingsystem.core.database import get_cursor
from tradingsystem.models.backtest import (
    BacktestConfig,
    BacktestRequest,
    BacktestResult,
    BacktestSummary,
)
from tradingsystem.services import chart_service
from tradingsystem.strategies.registry import StrategyRegistry

logger = logging.getLogger(__name__)


async def run_backtest(request: BacktestRequest) -> BacktestResult:
    """
    Run a backtest for a strategy.

    Args:
        request: Backtest configuration request

    Returns:
        BacktestResult with full results
    """
    # Get strategy instance
    instance = StrategyRegistry.get_instance(
        request.strategy_id,
        **request.strategy_params,
    )
    if not instance:
        raise ValueError(f"Strategy not found: {request.strategy_id}")

    # Validate strategy
    errors = instance.validate()
    if errors:
        raise ValueError(f"Strategy validation failed: {errors}")

    # Create config
    config = BacktestConfig(
        strategy_id=request.strategy_id,
        instrument=request.instrument,
        start_date=request.start_date,
        end_date=request.end_date,
        initial_capital=request.initial_capital,
        position_size_pct=request.position_size_pct,
        period=request.period,
    )

    # Fetch historical data
    logger.info(
        f"Fetching candles for {request.instrument} from {request.start_date} to {request.end_date}"
    )

    candles = await chart_service.get_chart_dataframe(
        instrument=request.instrument,
        period=request.period,
        start=request.start_date,
        end=request.end_date,
        limit=1000,  # RateService limit
    )

    if candles.empty:
        raise ValueError(
            f"No candle data available for {request.instrument} "
            f"from {request.start_date} to {request.end_date}"
        )

    logger.info(f"Retrieved {len(candles)} candles for backtest")

    # Run backtest
    engine = BacktestEngine(config)
    result = engine.run(instance, candles)

    # Save to database
    saved_result = await save_backtest_result(result)

    logger.info(
        f"Backtest complete: {result.metrics.total_trades} trades, "
        f"{result.metrics.total_return_pct:.2f}% return, "
        f"{result.metrics.win_rate:.1f}% win rate"
    )

    return saved_result


async def save_backtest_result(result: BacktestResult) -> BacktestResult:
    """Save backtest result to database."""
    async with get_cursor() as cur:
        # Serialize complex fields to JSON
        config_json = result.config.model_dump_json()
        metrics_json = result.metrics.model_dump_json()
        trades_json = json.dumps([t.model_dump(mode="json") for t in result.trades])
        equity_json = json.dumps([e.model_dump(mode="json") for e in result.equity_curve[-100:]])  # Last 100 points

        await cur.execute(
            """
            INSERT INTO strategy_runs (
                strategy_id, mode, started_at, ended_at, config, results
            ) VALUES (
                %s, %s, %s, %s, %s, %s
            )
            RETURNING id, started_at
            """,
            (
                result.strategy_id,
                "BACKTEST",
                result.start_date,
                result.end_date,
                json.dumps({
                    "config": json.loads(config_json),
                    "instrument": result.instrument,
                    "period": result.period,
                    "initial_capital": str(result.initial_capital),
                }),
                json.dumps({
                    "metrics": json.loads(metrics_json),
                    "final_capital": str(result.final_capital),
                    "trades": json.loads(trades_json),
                    "equity_curve_sample": json.loads(equity_json),
                }),
            ),
        )
        row = await cur.fetchone()
        await cur.connection.commit()

        result.id = row["id"]
        result.created_at = row["started_at"]

        return result


async def get_backtest(backtest_id: UUID) -> BacktestResult | None:
    """Get a backtest result by ID."""
    async with get_cursor() as cur:
        await cur.execute(
            """
            SELECT id, strategy_id, mode, started_at, ended_at, config, results
            FROM strategy_runs
            WHERE id = %s AND mode = 'BACKTEST'
            """,
            (backtest_id,),
        )
        row = await cur.fetchone()

        if not row:
            return None

        return _row_to_backtest_result(row)


async def list_backtests(
    strategy_id: str | None = None,
    instrument: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[BacktestSummary]:
    """List backtest summaries with optional filtering."""
    conditions = ["mode = 'BACKTEST'"]
    params: list[Any] = []

    if strategy_id:
        conditions.append("strategy_id = %s")
        params.append(strategy_id)

    if instrument:
        conditions.append("config->>'instrument' = %s")
        params.append(instrument)

    where_clause = " AND ".join(conditions)
    params.extend([limit, offset])

    async with get_cursor() as cur:
        await cur.execute(
            f"""
            SELECT id, strategy_id, started_at, ended_at, config, results
            FROM strategy_runs
            WHERE {where_clause}
            ORDER BY started_at DESC
            LIMIT %s OFFSET %s
            """,
            params,
        )
        rows = await cur.fetchall()

        summaries = []
        for row in rows:
            try:
                config = row["config"] or {}
                results = row["results"] or {}
                metrics = results.get("metrics", {})

                summaries.append(BacktestSummary(
                    id=row["id"],
                    strategy_id=row["strategy_id"],
                    instrument=config.get("instrument", "unknown"),
                    start_date=row["started_at"],
                    end_date=row["ended_at"],
                    total_return_pct=Decimal(str(metrics.get("total_return_pct", 0))),
                    sharpe_ratio=metrics.get("sharpe_ratio"),
                    max_drawdown_pct=Decimal(str(metrics.get("max_drawdown_pct", 0))),
                    total_trades=metrics.get("total_trades", 0),
                    win_rate=metrics.get("win_rate", 0),
                    created_at=row["started_at"],
                ))
            except Exception as e:
                logger.warning(f"Error parsing backtest {row['id']}: {e}")

        return summaries


async def delete_backtest(backtest_id: UUID) -> bool:
    """Delete a backtest result."""
    async with get_cursor() as cur:
        await cur.execute(
            """
            DELETE FROM strategy_runs
            WHERE id = %s AND mode = 'BACKTEST'
            """,
            (backtest_id,),
        )
        await cur.connection.commit()
        return cur.rowcount > 0


def _row_to_backtest_result(row: dict) -> BacktestResult:
    """Convert a database row to BacktestResult."""
    config_data = row["config"] or {}
    results_data = row["results"] or {}
    metrics_data = results_data.get("metrics", {})

    # Reconstruct config
    config = BacktestConfig(
        strategy_id=row["strategy_id"],
        instrument=config_data.get("instrument", "unknown"),
        start_date=row["started_at"],
        end_date=row["ended_at"],
        initial_capital=Decimal(str(config_data.get("initial_capital", 10000))),
        period=config_data.get("period", "M1"),
    )

    # Reconstruct metrics
    from tradingsystem.models.backtest import PerformanceMetrics
    metrics = PerformanceMetrics(
        total_return=Decimal(str(metrics_data.get("total_return", 0))),
        total_return_pct=Decimal(str(metrics_data.get("total_return_pct", 0))),
        sharpe_ratio=metrics_data.get("sharpe_ratio"),
        max_drawdown=Decimal(str(metrics_data.get("max_drawdown", 0))),
        max_drawdown_pct=Decimal(str(metrics_data.get("max_drawdown_pct", 0))),
        win_rate=metrics_data.get("win_rate", 0),
        profit_factor=metrics_data.get("profit_factor"),
        avg_win=Decimal(str(metrics_data["avg_win"])) if metrics_data.get("avg_win") else None,
        avg_loss=Decimal(str(metrics_data["avg_loss"])) if metrics_data.get("avg_loss") else None,
        avg_trade=Decimal(str(metrics_data["avg_trade"])) if metrics_data.get("avg_trade") else None,
        total_trades=metrics_data.get("total_trades", 0),
        winning_trades=metrics_data.get("winning_trades", 0),
        losing_trades=metrics_data.get("losing_trades", 0),
    )

    # Reconstruct trades (if available)
    from tradingsystem.models.backtest import BacktestTrade
    trades = []
    for t in results_data.get("trades", []):
        trades.append(BacktestTrade(
            entry_time=datetime.fromisoformat(t["entry_time"]),
            exit_time=datetime.fromisoformat(t["exit_time"]) if t.get("exit_time") else None,
            side=t["side"],
            entry_price=Decimal(str(t["entry_price"])),
            exit_price=Decimal(str(t["exit_price"])) if t.get("exit_price") else None,
            quantity=Decimal(str(t["quantity"])),
            pnl=Decimal(str(t["pnl"])) if t.get("pnl") else None,
            pnl_pct=Decimal(str(t["pnl_pct"])) if t.get("pnl_pct") else None,
            signal_reason=t.get("signal_reason", ""),
        ))

    return BacktestResult(
        id=row["id"],
        strategy_id=row["strategy_id"],
        instrument=config_data.get("instrument", "unknown"),
        period=config_data.get("period", "M1"),
        start_date=row["started_at"],
        end_date=row["ended_at"],
        initial_capital=config.initial_capital,
        final_capital=Decimal(str(results_data.get("final_capital", config.initial_capital))),
        config=config,
        metrics=metrics,
        trades=trades,
        created_at=row["started_at"],
    )
