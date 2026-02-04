"""Backtest models for strategy testing."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from tradingsystem.models.signal import SignalType


class BacktestConfig(BaseModel):
    """Configuration for a backtest run."""

    strategy_id: str
    instrument: str
    start_date: datetime
    end_date: datetime
    initial_capital: Decimal = Decimal("10000")
    position_size_pct: Decimal = Decimal("2.0")  # % of capital per trade
    max_positions: int = 1
    commission_pct: Decimal = Decimal("0.001")  # 0.1% per trade
    slippage_pct: Decimal = Decimal("0.0005")  # 0.05% slippage
    period: str = "M1"


class BacktestTrade(BaseModel):
    """A single trade in a backtest."""

    entry_time: datetime
    exit_time: datetime | None = None
    side: str  # "LONG" or "SHORT"
    entry_price: Decimal
    exit_price: Decimal | None = None
    quantity: Decimal
    pnl: Decimal | None = None
    pnl_pct: Decimal | None = None
    commission: Decimal = Decimal("0")
    signal_reason: str = ""


class EquityPoint(BaseModel):
    """A point on the equity curve."""

    time: datetime
    equity: Decimal
    drawdown: Decimal = Decimal("0")
    drawdown_pct: Decimal = Decimal("0")


class PerformanceMetrics(BaseModel):
    """Performance metrics for a backtest."""

    total_return: Decimal
    total_return_pct: Decimal
    annualized_return_pct: Decimal | None = None
    sharpe_ratio: float | None = None
    sortino_ratio: float | None = None
    max_drawdown: Decimal
    max_drawdown_pct: Decimal
    win_rate: float
    profit_factor: float | None = None
    avg_win: Decimal | None = None
    avg_loss: Decimal | None = None
    avg_trade: Decimal | None = None
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_trade_duration: float | None = None  # in minutes
    largest_win: Decimal | None = None
    largest_loss: Decimal | None = None


class BacktestResult(BaseModel):
    """Complete backtest results."""

    id: UUID | None = None
    strategy_id: str
    instrument: str
    period: str
    start_date: datetime
    end_date: datetime
    initial_capital: Decimal
    final_capital: Decimal
    config: BacktestConfig
    metrics: PerformanceMetrics
    trades: list[BacktestTrade] = []
    equity_curve: list[EquityPoint] = []
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class BacktestRequest(BaseModel):
    """API request to run a backtest."""

    strategy_id: str
    instrument: str
    start_date: datetime
    end_date: datetime
    initial_capital: Decimal = Decimal("10000")
    position_size_pct: Decimal = Decimal("2.0")
    period: str = "M1"
    strategy_params: dict[str, Any] = Field(default_factory=dict)


class BacktestSummary(BaseModel):
    """Summary of a backtest for listing."""

    id: UUID
    strategy_id: str
    instrument: str
    start_date: datetime
    end_date: datetime
    total_return_pct: Decimal
    sharpe_ratio: float | None
    max_drawdown_pct: Decimal
    total_trades: int
    win_rate: float
    created_at: datetime
