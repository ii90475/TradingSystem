"""Backtest engine for strategy simulation."""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pandas as pd

from tradingsystem.indicators import IndicatorRegistry, calculate_pandas_ta_indicator
from tradingsystem.models.backtest import (
    BacktestConfig,
    BacktestResult,
    BacktestTrade,
    EquityPoint,
    PerformanceMetrics,
)
from tradingsystem.models.signal import Signal, SignalType
from tradingsystem.strategies.base import BaseStrategy, StrategyContext

logger = logging.getLogger(__name__)


class Position:
    """Represents an open position during backtesting."""

    def __init__(
        self,
        side: str,
        entry_price: Decimal,
        quantity: Decimal,
        entry_time: datetime,
        signal_reason: str = "",
    ):
        self.side = side
        self.entry_price = entry_price
        self.quantity = quantity
        self.entry_time = entry_time
        self.signal_reason = signal_reason

    def calculate_pnl(self, current_price: Decimal) -> Decimal:
        """Calculate unrealized P&L."""
        if self.side == "LONG":
            return (current_price - self.entry_price) * self.quantity
        else:  # SHORT
            return (self.entry_price - current_price) * self.quantity

    def close(self, exit_price: Decimal, exit_time: datetime, commission: Decimal) -> BacktestTrade:
        """Close position and return trade record."""
        pnl = self.calculate_pnl(exit_price) - commission
        pnl_pct = (pnl / (self.entry_price * self.quantity)) * 100

        return BacktestTrade(
            entry_time=self.entry_time,
            exit_time=exit_time,
            side=self.side,
            entry_price=self.entry_price,
            exit_price=exit_price,
            quantity=self.quantity,
            pnl=pnl,
            pnl_pct=pnl_pct,
            commission=commission,
            signal_reason=self.signal_reason,
        )


class BacktestEngine:
    """
    Walk-forward backtest engine.

    Simulates strategy execution on historical data by:
    1. Walking through each candle chronologically
    2. Calculating indicators up to that point
    3. Running strategy to generate signals
    4. Simulating trade execution with slippage/commission
    5. Tracking equity curve and performance
    """

    def __init__(self, config: BacktestConfig):
        self.config = config
        self.capital = config.initial_capital
        self.position: Position | None = None
        self.trades: list[BacktestTrade] = []
        self.equity_curve: list[EquityPoint] = []
        self.peak_equity = config.initial_capital
        self.signals_generated = 0

    def run(
        self,
        strategy: BaseStrategy,
        candles: pd.DataFrame,
    ) -> BacktestResult:
        """
        Run backtest on historical data.

        Args:
            strategy: Strategy instance to test
            candles: DataFrame with OHLCV data (index=datetime)

        Returns:
            BacktestResult with trades, equity curve, and metrics
        """
        if candles.empty:
            raise ValueError("No candle data provided for backtest")

        logger.info(
            f"Starting backtest: {strategy.name} on {self.config.instrument} "
            f"from {self.config.start_date} to {self.config.end_date}"
        )

        # Calculate all indicators upfront for efficiency
        indicators = self._calculate_all_indicators(strategy, candles)

        # Walk forward through each candle
        for i in range(len(candles)):
            current_time = candles.index[i]
            current_candle = candles.iloc[i]
            current_price = Decimal(str(current_candle["close"]))

            # Get data up to current point (no look-ahead)
            historical_candles = candles.iloc[: i + 1]
            historical_indicators = {
                key: val.iloc[: i + 1] if hasattr(val, "iloc") else val
                for key, val in indicators.items()
            }

            # Build context for strategy
            context = StrategyContext(
                instrument=self.config.instrument,
                period=self.config.period,
                candles=historical_candles,
                indicators=historical_indicators,
                current_time=current_time,
                current_price=float(current_price),
            )

            # Generate signals
            signals = strategy.generate_signals(context)
            self.signals_generated += len(signals)

            # Process signals
            for signal in signals:
                self._process_signal(signal, current_price, current_time)

            # Record equity point
            equity = self._calculate_equity(current_price)
            drawdown, drawdown_pct = self._calculate_drawdown(equity)

            self.equity_curve.append(
                EquityPoint(
                    time=current_time,
                    equity=equity,
                    drawdown=drawdown,
                    drawdown_pct=drawdown_pct,
                )
            )

        # Close any remaining position at end
        if self.position:
            final_price = Decimal(str(candles.iloc[-1]["close"]))
            self._close_position(final_price, candles.index[-1])

        # Calculate performance metrics
        metrics = self._calculate_metrics()

        return BacktestResult(
            strategy_id=self.config.strategy_id,
            instrument=self.config.instrument,
            period=self.config.period,
            start_date=self.config.start_date,
            end_date=self.config.end_date,
            initial_capital=self.config.initial_capital,
            final_capital=self.capital,
            config=self.config,
            metrics=metrics,
            trades=self.trades,
            equity_curve=self.equity_curve,
            created_at=datetime.now(timezone.utc),
        )

    def _calculate_all_indicators(
        self,
        strategy: BaseStrategy,
        candles: pd.DataFrame,
    ) -> dict[str, pd.Series | pd.DataFrame]:
        """Calculate all required indicators for the full dataset."""
        indicators: dict[str, pd.Series | pd.DataFrame] = {}

        for config in strategy.required_indicators:
            try:
                custom_cls = IndicatorRegistry.get(config.indicator_type)
                if custom_cls:
                    instance = custom_cls()
                    result = instance.calculate(candles, **config.params)
                else:
                    result = calculate_pandas_ta_indicator(
                        candles,
                        config.indicator_type,
                        **config.params,
                    )

                if result is not None:
                    key = config.column_name or config.indicator_type
                    indicators[key] = result

            except Exception as e:
                logger.warning(f"Failed to calculate {config.indicator_type}: {e}")

        return indicators

    def _process_signal(
        self,
        signal: Signal,
        current_price: Decimal,
        current_time: datetime,
    ) -> None:
        """Process a trading signal."""
        if signal.signal_type == SignalType.HOLD:
            return

        # Apply slippage
        slippage = current_price * self.config.slippage_pct
        if signal.signal_type == SignalType.BUY:
            execution_price = current_price + slippage
        else:
            execution_price = current_price - slippage

        # Check if we need to close existing position
        if self.position:
            # Close if signal is opposite to position
            if (
                (signal.signal_type == SignalType.BUY and self.position.side == "SHORT")
                or (signal.signal_type == SignalType.SELL and self.position.side == "LONG")
            ):
                self._close_position(execution_price, current_time)

        # Open new position if no position exists
        if not self.position and signal.signal_type in (SignalType.BUY, SignalType.SELL):
            self._open_position(signal, execution_price, current_time)

    def _open_position(
        self,
        signal: Signal,
        price: Decimal,
        time: datetime,
    ) -> None:
        """Open a new position."""
        # Calculate position size
        position_value = self.capital * (self.config.position_size_pct / 100)
        quantity = position_value / price

        # Calculate commission
        commission = position_value * self.config.commission_pct
        self.capital -= commission

        side = "LONG" if signal.signal_type == SignalType.BUY else "SHORT"

        self.position = Position(
            side=side,
            entry_price=price,
            quantity=quantity,
            entry_time=time,
            signal_reason=signal.reason,
        )

        logger.debug(f"Opened {side} position at {price} ({quantity} units)")

    def _close_position(self, price: Decimal, time: datetime) -> None:
        """Close the current position."""
        if not self.position:
            return

        # Calculate commission
        position_value = price * self.position.quantity
        commission = position_value * self.config.commission_pct

        # Create trade record
        trade = self.position.close(price, time, commission)
        self.trades.append(trade)

        # Update capital
        self.capital += trade.pnl if trade.pnl else Decimal("0")
        self.capital -= commission

        logger.debug(f"Closed {self.position.side} position at {price}, P&L: {trade.pnl}")

        self.position = None

    def _calculate_equity(self, current_price: Decimal) -> Decimal:
        """Calculate current equity including unrealized P&L."""
        equity = self.capital
        if self.position:
            equity += self.position.calculate_pnl(current_price)
        return equity

    def _calculate_drawdown(self, equity: Decimal) -> tuple[Decimal, Decimal]:
        """Calculate current drawdown from peak."""
        if equity > self.peak_equity:
            self.peak_equity = equity

        drawdown = self.peak_equity - equity
        drawdown_pct = (drawdown / self.peak_equity) * 100 if self.peak_equity > 0 else Decimal("0")

        return drawdown, drawdown_pct

    def _calculate_metrics(self) -> PerformanceMetrics:
        """Calculate performance metrics from trades."""
        total_return = self.capital - self.config.initial_capital
        total_return_pct = (total_return / self.config.initial_capital) * 100

        # Calculate max drawdown
        max_drawdown = Decimal("0")
        max_drawdown_pct = Decimal("0")
        for point in self.equity_curve:
            if point.drawdown > max_drawdown:
                max_drawdown = point.drawdown
                max_drawdown_pct = point.drawdown_pct

        # Trade statistics
        winning_trades = [t for t in self.trades if t.pnl and t.pnl > 0]
        losing_trades = [t for t in self.trades if t.pnl and t.pnl < 0]

        total_trades = len(self.trades)
        num_winners = len(winning_trades)
        num_losers = len(losing_trades)

        win_rate = (num_winners / total_trades * 100) if total_trades > 0 else 0.0

        # Average win/loss
        avg_win = None
        avg_loss = None
        if winning_trades:
            avg_win = sum(t.pnl for t in winning_trades if t.pnl) / len(winning_trades)
        if losing_trades:
            avg_loss = sum(t.pnl for t in losing_trades if t.pnl) / len(losing_trades)

        # Profit factor
        profit_factor = None
        if losing_trades:
            total_wins = sum(t.pnl for t in winning_trades if t.pnl)
            total_losses = abs(sum(t.pnl for t in losing_trades if t.pnl))
            if total_losses > 0:
                profit_factor = float(total_wins / total_losses)

        # Average trade
        avg_trade = None
        if self.trades:
            avg_trade = sum(t.pnl for t in self.trades if t.pnl) / len(self.trades)

        # Largest win/loss
        largest_win = max((t.pnl for t in self.trades if t.pnl and t.pnl > 0), default=None)
        largest_loss = min((t.pnl for t in self.trades if t.pnl and t.pnl < 0), default=None)

        # Average trade duration
        avg_duration = None
        if self.trades:
            durations = []
            for t in self.trades:
                if t.exit_time:
                    duration = (t.exit_time - t.entry_time).total_seconds() / 60
                    durations.append(duration)
            if durations:
                avg_duration = sum(durations) / len(durations)

        # Sharpe ratio (simplified - assumes risk-free rate of 0)
        sharpe_ratio = None
        if len(self.equity_curve) > 1:
            returns = []
            for i in range(1, len(self.equity_curve)):
                prev_equity = self.equity_curve[i - 1].equity
                curr_equity = self.equity_curve[i].equity
                if prev_equity > 0:
                    ret = float((curr_equity - prev_equity) / prev_equity)
                    returns.append(ret)

            if returns:
                import statistics
                mean_return = statistics.mean(returns)
                std_return = statistics.stdev(returns) if len(returns) > 1 else 0
                if std_return > 0:
                    # Annualize (assuming daily returns, adjust for actual frequency)
                    sharpe_ratio = (mean_return / std_return) * (252 ** 0.5)

        return PerformanceMetrics(
            total_return=total_return,
            total_return_pct=total_return_pct,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            max_drawdown_pct=max_drawdown_pct,
            win_rate=win_rate,
            profit_factor=profit_factor,
            avg_win=avg_win,
            avg_loss=avg_loss,
            avg_trade=avg_trade,
            total_trades=total_trades,
            winning_trades=num_winners,
            losing_trades=num_losers,
            avg_trade_duration=avg_duration,
            largest_win=largest_win,
            largest_loss=largest_loss,
        )
