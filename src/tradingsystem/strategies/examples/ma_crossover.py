"""Moving Average Crossover Strategy.

A classic trend-following strategy that generates signals when
a fast moving average crosses above or below a slow moving average.

BUY: Fast MA crosses above Slow MA (bullish crossover)
SELL: Fast MA crosses below Slow MA (bearish crossover)
"""

import pandas as pd

from tradingsystem.models.signal import Signal, SignalType
from tradingsystem.strategies.base import BaseStrategy, IndicatorConfig, StrategyContext
from tradingsystem.strategies.registry import StrategyRegistry


@StrategyRegistry.register("ma_crossover")
class MACrossoverStrategy(BaseStrategy):
    """
    Moving Average Crossover Strategy.

    Generates buy signals when the fast MA crosses above the slow MA,
    and sell signals when the fast MA crosses below the slow MA.

    Parameters:
        fast_period: Period for the fast moving average (default: 10)
        slow_period: Period for the slow moving average (default: 20)
        ma_type: Type of moving average - 'sma' or 'ema' (default: 'ema')
    """

    name = "MA Crossover"
    description = "Trend-following strategy using moving average crossovers"
    version = "1.0.0"
    author = "TradingSystem"

    instruments = ["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD"]
    periods = ["M1", "M5", "15m", "1h"]

    default_params = {
        "fast_period": 10,
        "slow_period": 20,
        "ma_type": "ema",  # 'sma' or 'ema'
    }

    @property
    def required_indicators(self) -> list[IndicatorConfig]:
        """Dynamic indicator config based on parameters."""
        ma_type = self.params.get("ma_type", "ema")
        fast_period = self.params.get("fast_period", 10)
        slow_period = self.params.get("slow_period", 20)

        return [
            IndicatorConfig(
                indicator_type=ma_type,
                params={"length": fast_period},
                column_name="fast_ma",
            ),
            IndicatorConfig(
                indicator_type=ma_type,
                params={"length": slow_period},
                column_name="slow_ma",
            ),
        ]

    def generate_signals(self, context: StrategyContext) -> list[Signal]:
        """
        Generate crossover signals.

        Looks for MA crossovers in the most recent candles.
        """
        signals = []

        # Get indicator values
        fast_ma = context.indicators.get("fast_ma")
        slow_ma = context.indicators.get("slow_ma")

        if fast_ma is None or slow_ma is None:
            return signals

        # Need at least 2 data points to detect crossover
        if len(fast_ma) < 2 or len(slow_ma) < 2:
            return signals

        # Get current and previous values
        fast_current = fast_ma.iloc[-1]
        fast_prev = fast_ma.iloc[-2]
        slow_current = slow_ma.iloc[-1]
        slow_prev = slow_ma.iloc[-2]

        # Skip if any values are NaN
        if pd.isna(fast_current) or pd.isna(fast_prev) or pd.isna(slow_current) or pd.isna(slow_prev):
            return signals

        # Detect bullish crossover (fast crosses above slow)
        if fast_prev <= slow_prev and fast_current > slow_current:
            # Calculate signal strength based on crossover magnitude
            diff = (fast_current - slow_current) / slow_current
            strength = min(1.0, abs(diff) * 100)  # Scale to 0-1

            signals.append(self.create_signal(
                signal_type=SignalType.BUY,
                instrument=context.instrument,
                strength=strength,
                reason=f"Bullish MA crossover: {self.params['ma_type'].upper()}({self.params['fast_period']}) crossed above {self.params['ma_type'].upper()}({self.params['slow_period']})",
                metadata={
                    "fast_ma": float(fast_current),
                    "slow_ma": float(slow_current),
                    "crossover_type": "bullish",
                    "price": context.current_price,
                },
            ))

        # Detect bearish crossover (fast crosses below slow)
        elif fast_prev >= slow_prev and fast_current < slow_current:
            diff = (slow_current - fast_current) / slow_current
            strength = min(1.0, abs(diff) * 100)

            signals.append(self.create_signal(
                signal_type=SignalType.SELL,
                instrument=context.instrument,
                strength=strength,
                reason=f"Bearish MA crossover: {self.params['ma_type'].upper()}({self.params['fast_period']}) crossed below {self.params['ma_type'].upper()}({self.params['slow_period']})",
                metadata={
                    "fast_ma": float(fast_current),
                    "slow_ma": float(slow_current),
                    "crossover_type": "bearish",
                    "price": context.current_price,
                },
            ))

        return signals
