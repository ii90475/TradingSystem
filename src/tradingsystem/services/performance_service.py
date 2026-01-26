"""Performance tracking and metrics service."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from tradingsystem.core.database import get_cursor
from tradingsystem.core.oanda_trading import oanda_trading_client
from tradingsystem.core.config import settings
from tradingsystem.models.position import PositionStatus

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Performance metrics for a time period."""

    period: str  # "daily", "weekly", "monthly", "all_time"
    start_date: datetime
    end_date: datetime
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl: Decimal
    gross_profit: Decimal
    gross_loss: Decimal
    profit_factor: float | None
    average_win: Decimal
    average_loss: Decimal
    largest_win: Decimal
    largest_loss: Decimal
    average_trade: Decimal


@dataclass
class StrategyPerformance:
    """Performance metrics for a specific strategy."""

    strategy_id: str
    total_trades: int
    winning_trades: int
    win_rate: float
    total_pnl: Decimal
    average_pnl: Decimal
    sharpe_ratio: float | None
    max_drawdown: Decimal


@dataclass
class PortfolioSnapshot:
    """Current portfolio state."""

    timestamp: datetime
    account_balance: Decimal
    nav: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    open_positions: int
    margin_used: Decimal
    margin_available: Decimal
    daily_pnl: Decimal
    weekly_pnl: Decimal


async def get_portfolio_snapshot() -> PortfolioSnapshot:
    """
    Get current portfolio state combining local and Oanda data.

    Returns:
        PortfolioSnapshot with current state
    """
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())

    # Get Oanda account data
    try:
        account = await oanda_trading_client.get_account_summary()
        account_balance = account.balance
        nav = account.nav
        unrealized_pnl = account.unrealized_pnl
        margin_used = account.margin_used
        margin_available = account.margin_available
    except Exception as e:
        logger.warning(f"Failed to get Oanda account: {e}")
        account_balance = Decimal("0")
        nav = Decimal("0")
        unrealized_pnl = Decimal("0")
        margin_used = Decimal("0")
        margin_available = Decimal("0")

    # Get local position data
    async with get_cursor() as cur:
        # Open positions count
        await cur.execute(
            "SELECT COUNT(*) as count FROM positions WHERE status = %s",
            (PositionStatus.OPEN.value,),
        )
        row = await cur.fetchone()
        open_positions = row["count"]

        # Realized P&L (all time)
        await cur.execute(
            "SELECT COALESCE(SUM(pnl), 0) as total FROM positions WHERE status = %s",
            (PositionStatus.CLOSED.value,),
        )
        row = await cur.fetchone()
        realized_pnl = Decimal(str(row["total"]))

        # Daily P&L
        await cur.execute(
            """
            SELECT COALESCE(SUM(pnl), 0) as total
            FROM positions
            WHERE status = %s AND exit_time >= %s
            """,
            (PositionStatus.CLOSED.value, today_start),
        )
        row = await cur.fetchone()
        daily_pnl = Decimal(str(row["total"]))

        # Weekly P&L
        await cur.execute(
            """
            SELECT COALESCE(SUM(pnl), 0) as total
            FROM positions
            WHERE status = %s AND exit_time >= %s
            """,
            (PositionStatus.CLOSED.value, week_start),
        )
        row = await cur.fetchone()
        weekly_pnl = Decimal(str(row["total"]))

    return PortfolioSnapshot(
        timestamp=now,
        account_balance=account_balance,
        nav=nav,
        unrealized_pnl=unrealized_pnl,
        realized_pnl=realized_pnl,
        open_positions=open_positions,
        margin_used=margin_used,
        margin_available=margin_available,
        daily_pnl=daily_pnl,
        weekly_pnl=weekly_pnl,
    )


async def get_performance_metrics(
    period: str = "all_time",
    strategy_id: str | None = None,
) -> PerformanceMetrics:
    """
    Calculate performance metrics for a time period.

    Args:
        period: "daily", "weekly", "monthly", "all_time"
        strategy_id: Optional filter by strategy

    Returns:
        PerformanceMetrics for the period
    """
    now = datetime.now(timezone.utc)

    if period == "daily":
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "weekly":
        start_date = now - timedelta(days=now.weekday())
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "monthly":
        start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:  # all_time
        start_date = datetime(2020, 1, 1, tzinfo=timezone.utc)

    conditions = ["status = %s", "exit_time >= %s"]
    params: list[Any] = [PositionStatus.CLOSED.value, start_date]

    if strategy_id:
        conditions.append("strategy_id = %s")
        params.append(strategy_id)

    where_clause = " AND ".join(conditions)

    async with get_cursor() as cur:
        # Get all closed positions in period
        await cur.execute(
            f"""
            SELECT pnl, entry_price, quantity
            FROM positions
            WHERE {where_clause}
            ORDER BY exit_time
            """,
            params,
        )
        rows = await cur.fetchall()

    if not rows:
        return PerformanceMetrics(
            period=period,
            start_date=start_date,
            end_date=now,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0.0,
            total_pnl=Decimal("0"),
            gross_profit=Decimal("0"),
            gross_loss=Decimal("0"),
            profit_factor=None,
            average_win=Decimal("0"),
            average_loss=Decimal("0"),
            largest_win=Decimal("0"),
            largest_loss=Decimal("0"),
            average_trade=Decimal("0"),
        )

    # Calculate metrics
    pnls = [Decimal(str(row["pnl"] or 0)) for row in rows]
    total_trades = len(pnls)

    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    winning_trades = len(wins)
    losing_trades = len(losses)
    win_rate = winning_trades / total_trades if total_trades > 0 else 0.0

    total_pnl = sum(pnls)
    gross_profit = sum(wins) if wins else Decimal("0")
    gross_loss = abs(sum(losses)) if losses else Decimal("0")

    profit_factor = (
        float(gross_profit / gross_loss) if gross_loss > 0 else None
    )

    average_win = gross_profit / len(wins) if wins else Decimal("0")
    average_loss = gross_loss / len(losses) if losses else Decimal("0")
    largest_win = max(wins) if wins else Decimal("0")
    largest_loss = abs(min(losses)) if losses else Decimal("0")
    average_trade = total_pnl / total_trades if total_trades > 0 else Decimal("0")

    return PerformanceMetrics(
        period=period,
        start_date=start_date,
        end_date=now,
        total_trades=total_trades,
        winning_trades=winning_trades,
        losing_trades=losing_trades,
        win_rate=win_rate,
        total_pnl=total_pnl,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        profit_factor=profit_factor,
        average_win=average_win,
        average_loss=average_loss,
        largest_win=largest_win,
        largest_loss=largest_loss,
        average_trade=average_trade,
    )


async def get_strategy_performance(strategy_id: str) -> StrategyPerformance:
    """
    Get performance metrics for a specific strategy.

    Args:
        strategy_id: Strategy identifier

    Returns:
        StrategyPerformance metrics
    """
    async with get_cursor() as cur:
        await cur.execute(
            """
            SELECT
                COUNT(*) as total_trades,
                COUNT(*) FILTER (WHERE pnl > 0) as winning_trades,
                COALESCE(SUM(pnl), 0) as total_pnl,
                COALESCE(AVG(pnl), 0) as average_pnl,
                COALESCE(MIN(pnl), 0) as max_loss
            FROM positions
            WHERE strategy_id = %s AND status = %s
            """,
            (strategy_id, PositionStatus.CLOSED.value),
        )
        row = await cur.fetchone()

    total_trades = row["total_trades"]
    winning_trades = row["winning_trades"]
    win_rate = winning_trades / total_trades if total_trades > 0 else 0.0
    total_pnl = Decimal(str(row["total_pnl"]))
    average_pnl = Decimal(str(row["average_pnl"]))
    max_drawdown = abs(Decimal(str(row["max_loss"])))

    return StrategyPerformance(
        strategy_id=strategy_id,
        total_trades=total_trades,
        winning_trades=winning_trades,
        win_rate=win_rate,
        total_pnl=total_pnl,
        average_pnl=average_pnl,
        sharpe_ratio=None,  # Would need returns time series
        max_drawdown=max_drawdown,
    )


async def get_all_strategy_performance() -> list[StrategyPerformance]:
    """Get performance for all strategies with trades."""
    async with get_cursor() as cur:
        await cur.execute(
            """
            SELECT DISTINCT strategy_id
            FROM positions
            WHERE strategy_id IS NOT NULL AND status = %s
            """,
            (PositionStatus.CLOSED.value,),
        )
        rows = await cur.fetchall()

    results = []
    for row in rows:
        perf = await get_strategy_performance(row["strategy_id"])
        results.append(perf)

    return results


async def get_trade_history(
    limit: int = 50,
    strategy_id: str | None = None,
) -> list[dict]:
    """
    Get recent trade history.

    Args:
        limit: Maximum trades to return
        strategy_id: Optional filter

    Returns:
        List of trade records
    """
    conditions = ["status = %s"]
    params: list[Any] = [PositionStatus.CLOSED.value]

    if strategy_id:
        conditions.append("strategy_id = %s")
        params.append(strategy_id)

    where_clause = " AND ".join(conditions)
    params.append(limit)

    async with get_cursor() as cur:
        await cur.execute(
            f"""
            SELECT id, instrument, side, quantity, entry_price, exit_price,
                   entry_time, exit_time, pnl, pnl_percent, strategy_id
            FROM positions
            WHERE {where_clause}
            ORDER BY exit_time DESC
            LIMIT %s
            """,
            params,
        )
        rows = await cur.fetchall()

    return [
        {
            "id": str(row["id"]),
            "instrument": row["instrument"],
            "side": row["side"],
            "quantity": str(row["quantity"]),
            "entry_price": str(row["entry_price"]),
            "exit_price": str(row["exit_price"]),
            "entry_time": row["entry_time"].isoformat(),
            "exit_time": row["exit_time"].isoformat(),
            "pnl": str(row["pnl"]),
            "pnl_percent": str(row["pnl_percent"]),
            "strategy_id": row["strategy_id"],
        }
        for row in rows
    ]


async def get_equity_curve(days: int = 30) -> list[dict]:
    """
    Get equity curve data (cumulative P&L over time).

    Args:
        days: Number of days to include

    Returns:
        List of {date, cumulative_pnl} points
    """
    start_date = datetime.now(timezone.utc) - timedelta(days=days)

    async with get_cursor() as cur:
        await cur.execute(
            """
            SELECT
                DATE(exit_time) as date,
                SUM(pnl) as daily_pnl
            FROM positions
            WHERE status = %s AND exit_time >= %s
            GROUP BY DATE(exit_time)
            ORDER BY date
            """,
            (PositionStatus.CLOSED.value, start_date),
        )
        rows = await cur.fetchall()

    # Calculate cumulative P&L
    cumulative = Decimal("0")
    curve = []
    for row in rows:
        cumulative += Decimal(str(row["daily_pnl"]))
        curve.append({
            "date": str(row["date"]),
            "daily_pnl": str(row["daily_pnl"]),
            "cumulative_pnl": str(cumulative),
        })

    return curve
