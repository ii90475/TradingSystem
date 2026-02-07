"""MACD Divergence Strategy.

A momentum/reversal strategy that generates signals based on
divergence between price and MACD.

Bullish divergence: Price makes lower low, MACD makes higher low → BUY
Bearish divergence: Price makes higher high, MACD makes lower high → SELL
"""

import pandas as pd
import numpy as np

from tradingsystem.models.signal import Signal, SignalType
from tradingsystem.strategies.base import BaseStrategy, IndicatorConfig, StrategyContext
from tradingsystem.strategies.registry import StrategyRegistry


@StrategyRegistry.register("macd_divergence")
class MACDDivergenceStrategy(BaseStrategy):
    """
    MACD Divergence Strategy.

    Generates buy signals on bullish divergence (price lower low, MACD higher low),
    and sell signals on bearish divergence (price higher high, MACD lower high).

    Parameters:
        macd_fast: MACD fast period (default: 12)
        macd_slow: MACD slow period (default: 26)
        macd_signal: MACD signal period (default: 9)
        lookback: Periods to find swing points (default: 20)
        min_divergence: Minimum price divergence (default: 0.0001)
    """

    name = "MACD Divergence"
    description = "Momentum/reversal strategy using MACD-price divergence"
    version = "1.0.0"
    author = "TradingSystem"

    instruments = ["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD"]
    periods = ["M15", "1h", "4h", "D"]

    default_params = {
        "macd_fast": 12,
        "macd_slow": 26,
        "macd_signal": 9,
        "lookback": 20,
        "min_divergence": 0.0001,
    }

    @property
    def required_indicators(self) -> list[IndicatorConfig]:
        """Dynamic indicator config based on parameters."""
        macd_fast = self.params.get("macd_fast", 12)
        macd_slow = self.params.get("macd_slow", 26)
        macd_signal = self.params.get("macd_signal", 9)

        return [
            IndicatorConfig(
                indicator_type="macd",
                params={
                    "fast": macd_fast,
                    "slow": macd_slow,
                    "signal": macd_signal,
                },
                column_name="macd",
            ),
        ]

    def _find_swing_lows(self, series: pd.Series, lookback: int) -> list[tuple[int, float]]:
        """
        Find swing lows in the series.

        Returns list of (index, value) tuples for swing low points.
        """
        swing_lows = []
        window = max(3, lookback // 4)  # Window for local minimum

        for i in range(window, len(series) - window):
            val = series.iloc[i]
            if pd.isna(val):
                continue

            # Check if this is a local minimum
            left = series.iloc[i - window:i]
            right = series.iloc[i + 1:i + window + 1]

            if len(left) > 0 and len(right) > 0:
                if val <= left.min() and val <= right.min():
                    swing_lows.append((i, val))

        return swing_lows

    def _find_swing_highs(self, series: pd.Series, lookback: int) -> list[tuple[int, float]]:
        """
        Find swing highs in the series.

        Returns list of (index, value) tuples for swing high points.
        """
        swing_highs = []
        window = max(3, lookback // 4)

        for i in range(window, len(series) - window):
            val = series.iloc[i]
            if pd.isna(val):
                continue

            # Check if this is a local maximum
            left = series.iloc[i - window:i]
            right = series.iloc[i + 1:i + window + 1]

            if len(left) > 0 and len(right) > 0:
                if val >= left.max() and val >= right.max():
                    swing_highs.append((i, val))

        return swing_highs

    def generate_signals(self, context: StrategyContext) -> list[Signal]:
        """
        Generate MACD divergence signals.

        Looks for divergence between price and MACD swing points.
        """
        signals = []

        # Get MACD values
        macd_data = context.indicators.get("macd")
        if macd_data is None:
            return signals

        # MACD returns DataFrame with MACD, signal, histogram columns
        if isinstance(macd_data, pd.DataFrame):
            macd_line = macd_data.get("MACD")
            if macd_line is None:
                macd_line = macd_data.get("macd")
            macd_hist = macd_data.get("MACDh")
            if macd_hist is None:
                macd_hist = macd_data.get("histogram")
        else:
            macd_line = macd_data
            macd_hist = context.indicators.get("macd_histogram")

        if macd_line is None:
            return signals

        lookback = self.params.get("lookback", 20)
        min_divergence = self.params.get("min_divergence", 0.0001)

        # Need enough data for swing detection
        if len(context.candles) < lookback + 10:
            return signals

        close = context.candles["close"]

        # Look at recent data for swing points
        recent_close = close.iloc[-lookback:]
        recent_macd = macd_line.iloc[-lookback:]

        # Find swing points in recent data
        price_lows = self._find_swing_lows(recent_close, lookback)
        price_highs = self._find_swing_highs(recent_close, lookback)
        macd_lows = self._find_swing_lows(recent_macd, lookback)
        macd_highs = self._find_swing_highs(recent_macd, lookback)

        # Check for bullish divergence (price lower low, MACD higher low)
        if len(price_lows) >= 2 and len(macd_lows) >= 2:
            # Get the two most recent swing lows
            price_low1 = price_lows[-2]  # Earlier low
            price_low2 = price_lows[-1]  # More recent low
            macd_low1 = macd_lows[-2]
            macd_low2 = macd_lows[-1]

            # Price makes lower low
            price_diff = price_low2[1] - price_low1[1]
            # MACD makes higher low
            macd_diff = macd_low2[1] - macd_low1[1]

            if price_diff < -min_divergence and macd_diff > 0:
                # Bullish divergence detected
                strength = min(1.0, abs(macd_diff) * 100 + 0.5)

                signals.append(self.create_signal(
                    signal_type=SignalType.BUY,
                    instrument=context.instrument,
                    strength=strength,
                    reason="Bullish MACD divergence: price lower low, MACD higher low",
                    metadata={
                        "divergence_type": "bullish",
                        "price_low1": float(price_low1[1]),
                        "price_low2": float(price_low2[1]),
                        "macd_low1": float(macd_low1[1]),
                        "macd_low2": float(macd_low2[1]),
                        "price_diff": float(price_diff),
                        "macd_diff": float(macd_diff),
                        "price": context.current_price,
                    },
                ))

        # Check for bearish divergence (price higher high, MACD lower high)
        if len(price_highs) >= 2 and len(macd_highs) >= 2:
            # Get the two most recent swing highs
            price_high1 = price_highs[-2]  # Earlier high
            price_high2 = price_highs[-1]  # More recent high
            macd_high1 = macd_highs[-2]
            macd_high2 = macd_highs[-1]

            # Price makes higher high
            price_diff = price_high2[1] - price_high1[1]
            # MACD makes lower high
            macd_diff = macd_high2[1] - macd_high1[1]

            if price_diff > min_divergence and macd_diff < 0:
                # Bearish divergence detected
                strength = min(1.0, abs(macd_diff) * 100 + 0.5)

                signals.append(self.create_signal(
                    signal_type=SignalType.SELL,
                    instrument=context.instrument,
                    strength=strength,
                    reason="Bearish MACD divergence: price higher high, MACD lower high",
                    metadata={
                        "divergence_type": "bearish",
                        "price_high1": float(price_high1[1]),
                        "price_high2": float(price_high2[1]),
                        "macd_high1": float(macd_high1[1]),
                        "macd_high2": float(macd_high2[1]),
                        "price_diff": float(price_diff),
                        "macd_diff": float(macd_diff),
                        "price": context.current_price,
                    },
                ))

        return signals

    def validate(self) -> list[str]:
        """Validate strategy parameters."""
        errors = super().validate()

        macd_fast = self.params.get("macd_fast", 12)
        macd_slow = self.params.get("macd_slow", 26)
        lookback = self.params.get("lookback", 20)

        if macd_fast >= macd_slow:
            errors.append("MACD fast period must be less than slow period")

        if macd_fast < 2:
            errors.append("MACD fast period must be at least 2")

        if lookback < 10:
            errors.append("Lookback period must be at least 10")

        return errors
