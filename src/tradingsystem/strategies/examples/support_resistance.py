"""Support/Resistance Breakout Strategy.

A price action/breakout strategy that detects horizontal support and
resistance levels using pivot points.

BUY: Price breaks above resistance with momentum
SELL: Price breaks below support with momentum
"""

import pandas as pd
import numpy as np

from tradingsystem.models.signal import Signal, SignalType
from tradingsystem.strategies.base import BaseStrategy, IndicatorConfig, StrategyContext
from tradingsystem.strategies.registry import StrategyRegistry


@StrategyRegistry.register("support_resistance")
class SupportResistanceStrategy(BaseStrategy):
    """
    Support/Resistance Breakout Strategy.

    Detects horizontal S/R levels using pivot points and generates signals
    when price breaks through these levels with momentum.

    Parameters:
        lookback: Periods to find S/R levels (default: 50)
        tolerance: Price tolerance for level detection as ratio (default: 0.0005)
        min_touches: Minimum touches to confirm level (default: 2)
        breakout_pct: Min % move beyond level for breakout (default: 0.001)
    """

    name = "Support/Resistance Breakout"
    description = "Price action strategy using support/resistance breakouts"
    version = "1.0.0"
    author = "TradingSystem"

    instruments = ["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD"]
    periods = ["M15", "1h", "4h", "D"]

    default_params = {
        "lookback": 50,
        "tolerance": 0.0005,  # 0.05% tolerance
        "min_touches": 2,
        "breakout_pct": 0.001,  # 0.1% breakout
    }

    @property
    def required_indicators(self) -> list[IndicatorConfig]:
        """No external indicators required - uses raw price action."""
        return []

    def _find_pivot_points(self, candles: pd.DataFrame, window: int = 5) -> tuple[list[float], list[float]]:
        """
        Find pivot high and low points in price data.

        Returns (pivot_highs, pivot_lows) as lists of price levels.
        """
        highs = candles["high"]
        lows = candles["low"]

        pivot_highs = []
        pivot_lows = []

        for i in range(window, len(candles) - window):
            # Check for pivot high
            is_pivot_high = True
            current_high = highs.iloc[i]
            for j in range(1, window + 1):
                if highs.iloc[i - j] >= current_high or highs.iloc[i + j] >= current_high:
                    is_pivot_high = False
                    break
            if is_pivot_high:
                pivot_highs.append(current_high)

            # Check for pivot low
            is_pivot_low = True
            current_low = lows.iloc[i]
            for j in range(1, window + 1):
                if lows.iloc[i - j] <= current_low or lows.iloc[i + j] <= current_low:
                    is_pivot_low = False
                    break
            if is_pivot_low:
                pivot_lows.append(current_low)

        return pivot_highs, pivot_lows

    def _cluster_levels(self, levels: list[float], tolerance: float) -> list[tuple[float, int]]:
        """
        Cluster nearby price levels together.

        Returns list of (level, touch_count) tuples.
        """
        if not levels:
            return []

        sorted_levels = sorted(levels)
        clusters = []
        current_cluster = [sorted_levels[0]]

        for level in sorted_levels[1:]:
            # Check if level is within tolerance of cluster mean
            cluster_mean = np.mean(current_cluster)
            if abs(level - cluster_mean) / cluster_mean <= tolerance:
                current_cluster.append(level)
            else:
                # Save current cluster and start new one
                clusters.append((np.mean(current_cluster), len(current_cluster)))
                current_cluster = [level]

        # Don't forget the last cluster
        if current_cluster:
            clusters.append((np.mean(current_cluster), len(current_cluster)))

        return clusters

    def generate_signals(self, context: StrategyContext) -> list[Signal]:
        """
        Generate support/resistance breakout signals.

        Detects S/R levels and looks for breakouts with momentum.
        """
        signals = []

        lookback = self.params.get("lookback", 50)
        tolerance = self.params.get("tolerance", 0.0005)
        min_touches = self.params.get("min_touches", 2)
        breakout_pct = self.params.get("breakout_pct", 0.001)

        # Need enough data
        if len(context.candles) < lookback + 10:
            return signals

        # Get recent candles for S/R detection
        candles = context.candles.iloc[-lookback:]

        # Find pivot points
        pivot_highs, pivot_lows = self._find_pivot_points(candles)

        # Cluster into S/R levels
        resistance_levels = self._cluster_levels(pivot_highs, tolerance)
        support_levels = self._cluster_levels(pivot_lows, tolerance)

        # Filter by minimum touches
        resistance_levels = [(level, count) for level, count in resistance_levels if count >= min_touches]
        support_levels = [(level, count) for level, count in support_levels if count >= min_touches]

        if not resistance_levels and not support_levels:
            return signals

        # Get current and previous price
        close_current = context.candles["close"].iloc[-1]
        close_prev = context.candles["close"].iloc[-2]
        high_current = context.candles["high"].iloc[-1]
        low_current = context.candles["low"].iloc[-1]

        if pd.isna(close_current) or pd.isna(close_prev):
            return signals

        # Check for resistance breakout (BUY)
        for resistance, touches in resistance_levels:
            # Price was below resistance, now breaking above
            if close_prev <= resistance:
                breakout_amount = (high_current - resistance) / resistance
                if breakout_amount >= breakout_pct:
                    # Calculate strength based on touches and breakout magnitude
                    touch_factor = min(1.0, touches / 5)  # More touches = stronger level
                    breakout_factor = min(1.0, breakout_amount / (breakout_pct * 3))
                    strength = 0.4 + touch_factor * 0.3 + breakout_factor * 0.3

                    signals.append(self.create_signal(
                        signal_type=SignalType.BUY,
                        instrument=context.instrument,
                        strength=strength,
                        reason=f"Resistance breakout at {resistance:.5f} ({touches} touches)",
                        metadata={
                            "level": float(resistance),
                            "level_type": "resistance",
                            "touches": touches,
                            "breakout_amount": float(breakout_amount),
                            "close": float(close_current),
                            "high": float(high_current),
                            "price": context.current_price,
                        },
                    ))
                    break  # Only one signal per bar

        # Check for support breakdown (SELL)
        for support, touches in support_levels:
            # Price was above support, now breaking below
            if close_prev >= support:
                breakout_amount = (support - low_current) / support
                if breakout_amount >= breakout_pct:
                    # Calculate strength based on touches and breakout magnitude
                    touch_factor = min(1.0, touches / 5)
                    breakout_factor = min(1.0, breakout_amount / (breakout_pct * 3))
                    strength = 0.4 + touch_factor * 0.3 + breakout_factor * 0.3

                    signals.append(self.create_signal(
                        signal_type=SignalType.SELL,
                        instrument=context.instrument,
                        strength=strength,
                        reason=f"Support breakdown at {support:.5f} ({touches} touches)",
                        metadata={
                            "level": float(support),
                            "level_type": "support",
                            "touches": touches,
                            "breakout_amount": float(breakout_amount),
                            "close": float(close_current),
                            "low": float(low_current),
                            "price": context.current_price,
                        },
                    ))
                    break  # Only one signal per bar

        return signals

    def validate(self) -> list[str]:
        """Validate strategy parameters."""
        errors = super().validate()

        lookback = self.params.get("lookback", 50)
        tolerance = self.params.get("tolerance", 0.0005)
        min_touches = self.params.get("min_touches", 2)
        breakout_pct = self.params.get("breakout_pct", 0.001)

        if lookback < 20:
            errors.append("Lookback period must be at least 20")

        if tolerance <= 0 or tolerance > 0.01:
            errors.append("Tolerance must be between 0 and 0.01 (1%)")

        if min_touches < 1:
            errors.append("Minimum touches must be at least 1")

        if breakout_pct <= 0 or breakout_pct > 0.05:
            errors.append("Breakout percentage must be between 0 and 0.05 (5%)")

        return errors
