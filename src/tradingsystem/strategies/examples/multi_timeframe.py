"""Multi-Timeframe Trend Strategy.

A trend alignment strategy that checks trend on higher timeframe
and only takes trades in direction of the higher TF trend.

BUY: Higher TF uptrend + lower TF bullish EMA crossover
SELL: Higher TF downtrend + lower TF bearish EMA crossover
"""

import pandas as pd

from tradingsystem.models.signal import Signal, SignalType
from tradingsystem.strategies.base import BaseStrategy, IndicatorConfig, StrategyContext
from tradingsystem.strategies.registry import StrategyRegistry


@StrategyRegistry.register("multi_timeframe")
class MultiTimeframeStrategy(BaseStrategy):
    """
    Multi-Timeframe Trend Strategy.

    Only takes trades when lower timeframe signals align with higher
    timeframe trend direction. Uses EMA for trend determination.

    Parameters:
        trend_ema: EMA period for trend (default: 50)
        entry_ema_fast: Fast EMA for entry (default: 10)
        entry_ema_slow: Slow EMA for entry (default: 20)
        htf_multiplier: Higher TF multiplier (default: 4)

    Note: This strategy simulates higher TF data by aggregating
    candles with the htf_multiplier. For production, consider
    fetching actual higher TF data.
    """

    name = "Multi-Timeframe Trend"
    description = "Trend alignment strategy using multiple timeframes"
    version = "1.0.0"
    author = "TradingSystem"

    instruments = ["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD"]
    periods = ["M5", "M15", "1h"]

    default_params = {
        "trend_ema": 50,
        "entry_ema_fast": 10,
        "entry_ema_slow": 20,
        "htf_multiplier": 4,  # e.g., 4x M15 = H1
    }

    @property
    def required_indicators(self) -> list[IndicatorConfig]:
        """Dynamic indicator config based on parameters."""
        entry_fast = self.params.get("entry_ema_fast", 10)
        entry_slow = self.params.get("entry_ema_slow", 20)
        trend_ema = self.params.get("trend_ema", 50)

        return [
            IndicatorConfig(
                indicator_type="ema",
                params={"length": entry_fast},
                column_name="ema_fast",
            ),
            IndicatorConfig(
                indicator_type="ema",
                params={"length": entry_slow},
                column_name="ema_slow",
            ),
            IndicatorConfig(
                indicator_type="ema",
                params={"length": trend_ema},
                column_name="ema_trend",
            ),
        ]

    def _aggregate_to_htf(self, candles: pd.DataFrame, multiplier: int) -> pd.DataFrame:
        """
        Aggregate candles to simulate higher timeframe.

        Groups candles by multiplier and creates OHLCV bars.
        """
        if multiplier <= 1:
            return candles

        # Create group labels (0, 0, 0, 0, 1, 1, 1, 1, ...)
        groups = [i // multiplier for i in range(len(candles))]

        htf_candles = candles.copy()
        htf_candles["_group"] = groups

        # Aggregate OHLCV
        aggregated = htf_candles.groupby("_group").agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum" if "volume" in candles.columns else "first",
        })

        return aggregated

    def _calculate_ema(self, series: pd.Series, period: int) -> pd.Series:
        """Calculate EMA for a series."""
        return series.ewm(span=period, adjust=False).mean()

    def generate_signals(self, context: StrategyContext) -> list[Signal]:
        """
        Generate multi-timeframe trend signals.

        Only signals when lower TF entry aligns with higher TF trend.
        """
        signals = []

        # Get lower TF EMA values
        ema_fast = context.indicators.get("ema_fast")
        ema_slow = context.indicators.get("ema_slow")
        ema_trend = context.indicators.get("ema_trend")

        if ema_fast is None or ema_slow is None or ema_trend is None:
            return signals

        # Need at least 2 data points for crossover
        if len(ema_fast) < 2 or len(ema_slow) < 2:
            return signals

        htf_multiplier = self.params.get("htf_multiplier", 4)
        trend_ema_period = self.params.get("trend_ema", 50)

        # Calculate higher TF trend
        min_htf_candles = htf_multiplier * (trend_ema_period + 10)
        if len(context.candles) < min_htf_candles:
            return signals

        # Aggregate candles to higher TF
        htf_candles = self._aggregate_to_htf(context.candles, htf_multiplier)

        # Calculate trend EMA on HTF
        htf_close = htf_candles["close"]
        htf_ema = self._calculate_ema(htf_close, trend_ema_period)

        if len(htf_ema) < 2:
            return signals

        # Determine HTF trend
        htf_close_current = htf_close.iloc[-1]
        htf_ema_current = htf_ema.iloc[-1]

        if pd.isna(htf_close_current) or pd.isna(htf_ema_current):
            return signals

        htf_uptrend = htf_close_current > htf_ema_current
        htf_downtrend = htf_close_current < htf_ema_current

        # Get lower TF current and previous values
        fast_current = ema_fast.iloc[-1]
        fast_prev = ema_fast.iloc[-2]
        slow_current = ema_slow.iloc[-1]
        slow_prev = ema_slow.iloc[-2]

        if pd.isna(fast_current) or pd.isna(fast_prev) or pd.isna(slow_current) or pd.isna(slow_prev):
            return signals

        # Detect lower TF crossovers
        ltf_bullish_cross = fast_prev <= slow_prev and fast_current > slow_current
        ltf_bearish_cross = fast_prev >= slow_prev and fast_current < slow_current

        # Calculate trend strength
        htf_trend_strength = abs(htf_close_current - htf_ema_current) / htf_ema_current * 100
        ltf_cross_strength = abs(fast_current - slow_current) / slow_current * 100

        # BUY: HTF uptrend + LTF bullish crossover
        if htf_uptrend and ltf_bullish_cross:
            strength = min(1.0, 0.5 + htf_trend_strength * 0.1 + ltf_cross_strength * 0.1)

            signals.append(self.create_signal(
                signal_type=SignalType.BUY,
                instrument=context.instrument,
                strength=strength,
                reason=f"Multi-TF bullish: HTF uptrend + LTF EMA crossover",
                metadata={
                    "htf_trend": "up",
                    "htf_close": float(htf_close_current),
                    "htf_ema": float(htf_ema_current),
                    "htf_trend_strength": float(htf_trend_strength),
                    "ltf_ema_fast": float(fast_current),
                    "ltf_ema_slow": float(slow_current),
                    "ltf_cross_strength": float(ltf_cross_strength),
                    "htf_multiplier": htf_multiplier,
                    "price": context.current_price,
                },
            ))

        # SELL: HTF downtrend + LTF bearish crossover
        elif htf_downtrend and ltf_bearish_cross:
            strength = min(1.0, 0.5 + htf_trend_strength * 0.1 + ltf_cross_strength * 0.1)

            signals.append(self.create_signal(
                signal_type=SignalType.SELL,
                instrument=context.instrument,
                strength=strength,
                reason=f"Multi-TF bearish: HTF downtrend + LTF EMA crossover",
                metadata={
                    "htf_trend": "down",
                    "htf_close": float(htf_close_current),
                    "htf_ema": float(htf_ema_current),
                    "htf_trend_strength": float(htf_trend_strength),
                    "ltf_ema_fast": float(fast_current),
                    "ltf_ema_slow": float(slow_current),
                    "ltf_cross_strength": float(ltf_cross_strength),
                    "htf_multiplier": htf_multiplier,
                    "price": context.current_price,
                },
            ))

        return signals

    def validate(self) -> list[str]:
        """Validate strategy parameters."""
        errors = super().validate()

        entry_fast = self.params.get("entry_ema_fast", 10)
        entry_slow = self.params.get("entry_ema_slow", 20)
        trend_ema = self.params.get("trend_ema", 50)
        htf_multiplier = self.params.get("htf_multiplier", 4)

        if entry_fast >= entry_slow:
            errors.append("Entry fast EMA must be less than entry slow EMA")

        if entry_slow >= trend_ema:
            errors.append("Entry slow EMA should be less than trend EMA for clarity")

        if htf_multiplier < 2:
            errors.append("HTF multiplier must be at least 2")

        if htf_multiplier > 20:
            errors.append("HTF multiplier should not exceed 20")

        return errors
