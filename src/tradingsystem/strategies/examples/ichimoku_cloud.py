"""Ichimoku Cloud Strategy.

A trend-following strategy using the Ichimoku Kinko Hyo indicator system.

BUY: Price breaks above cloud, Tenkan crosses above Kijun
SELL: Price breaks below cloud, Tenkan crosses below Kijun
"""

import pandas as pd

from tradingsystem.models.signal import Signal, SignalType
from tradingsystem.strategies.base import BaseStrategy, IndicatorConfig, StrategyContext
from tradingsystem.strategies.registry import StrategyRegistry


@StrategyRegistry.register("ichimoku_cloud")
class IchimokuCloudStrategy(BaseStrategy):
    """
    Ichimoku Cloud Strategy.

    Generates buy signals when price breaks above the cloud with TK cross,
    and sell signals when price breaks below the cloud with TK cross.

    Parameters:
        tenkan_period: Tenkan-sen (conversion line) period (default: 9)
        kijun_period: Kijun-sen (base line) period (default: 26)
        senkou_b_period: Senkou Span B period (default: 52)
    """

    name = "Ichimoku Cloud"
    description = "Trend-following strategy using Ichimoku Kinko Hyo"
    version = "1.0.0"
    author = "TradingSystem"

    instruments = ["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD"]
    periods = ["1h", "4h", "D"]

    default_params = {
        "tenkan_period": 9,
        "kijun_period": 26,
        "senkou_b_period": 52,
    }

    @property
    def required_indicators(self) -> list[IndicatorConfig]:
        """Dynamic indicator config based on parameters."""
        tenkan_period = self.params.get("tenkan_period", 9)
        kijun_period = self.params.get("kijun_period", 26)
        senkou_b_period = self.params.get("senkou_b_period", 52)

        return [
            IndicatorConfig(
                indicator_type="ichimoku",
                params={
                    "tenkan": tenkan_period,
                    "kijun": kijun_period,
                    "senkou": senkou_b_period,
                },
                column_name="ichimoku",
            ),
        ]

    def generate_signals(self, context: StrategyContext) -> list[Signal]:
        """
        Generate Ichimoku Cloud signals.

        Looks for price-cloud breakouts with TK crosses.
        """
        signals = []

        # Get Ichimoku values
        ichimoku = context.indicators.get("ichimoku")
        if ichimoku is None:
            return signals

        # Ichimoku returns DataFrame with multiple columns
        if isinstance(ichimoku, pd.DataFrame):
            tenkan = ichimoku.get("tenkan")
            if tenkan is None:
                tenkan = ichimoku.get("ISA_9")
            kijun = ichimoku.get("kijun")
            if kijun is None:
                kijun = ichimoku.get("ISB_26")
            senkou_a = ichimoku.get("senkou_a")
            if senkou_a is None:
                senkou_a = ichimoku.get("ITS_9")
            senkou_b = ichimoku.get("senkou_b")
            if senkou_b is None:
                senkou_b = ichimoku.get("IKS_26")
        else:
            tenkan = context.indicators.get("ichimoku_tenkan")
            kijun = context.indicators.get("ichimoku_kijun")
            senkou_a = context.indicators.get("ichimoku_senkou_a")
            senkou_b = context.indicators.get("ichimoku_senkou_b")

        if tenkan is None or kijun is None or senkou_a is None or senkou_b is None:
            return signals

        # Need at least 2 data points
        if len(tenkan) < 2 or len(context.candles) < 2:
            return signals

        # Get current and previous values
        close = context.candles["close"]
        close_current = close.iloc[-1]
        close_prev = close.iloc[-2]

        tenkan_current = tenkan.iloc[-1]
        tenkan_prev = tenkan.iloc[-2]
        kijun_current = kijun.iloc[-1]
        kijun_prev = kijun.iloc[-2]
        senkou_a_current = senkou_a.iloc[-1]
        senkou_b_current = senkou_b.iloc[-1]

        # Skip if any values are NaN
        values = [close_current, close_prev, tenkan_current, tenkan_prev,
                  kijun_current, kijun_prev, senkou_a_current, senkou_b_current]
        if any(pd.isna(v) for v in values):
            return signals

        # Determine cloud boundaries
        cloud_top = max(senkou_a_current, senkou_b_current)
        cloud_bottom = min(senkou_a_current, senkou_b_current)
        cloud_thickness = cloud_top - cloud_bottom

        # Calculate cloud strength (thicker cloud = stronger signal)
        price_range = context.candles["high"].iloc[-20:].max() - context.candles["low"].iloc[-20:].min()
        if price_range > 0:
            cloud_strength = min(1.0, cloud_thickness / price_range * 2)
        else:
            cloud_strength = 0.5

        # Detect TK cross (Tenkan crosses Kijun)
        tk_bullish_cross = tenkan_prev <= kijun_prev and tenkan_current > kijun_current
        tk_bearish_cross = tenkan_prev >= kijun_prev and tenkan_current < kijun_current

        # Detect price-cloud relationship
        price_above_cloud = close_current > cloud_top
        price_below_cloud = close_current < cloud_bottom
        price_was_in_cloud = cloud_bottom <= close_prev <= cloud_top

        # BUY: Price breaks above cloud OR TK bullish cross above cloud
        if price_above_cloud:
            if tk_bullish_cross or (close_prev <= cloud_top and close_current > cloud_top):
                strength = min(1.0, 0.5 + cloud_strength * 0.5)

                reason_parts = []
                if close_prev <= cloud_top and close_current > cloud_top:
                    reason_parts.append("price broke above cloud")
                if tk_bullish_cross:
                    reason_parts.append("Tenkan crossed above Kijun")

                signals.append(self.create_signal(
                    signal_type=SignalType.BUY,
                    instrument=context.instrument,
                    strength=strength,
                    reason=f"Ichimoku bullish: {', '.join(reason_parts)}",
                    metadata={
                        "close": float(close_current),
                        "tenkan": float(tenkan_current),
                        "kijun": float(kijun_current),
                        "senkou_a": float(senkou_a_current),
                        "senkou_b": float(senkou_b_current),
                        "cloud_top": float(cloud_top),
                        "cloud_bottom": float(cloud_bottom),
                        "cloud_thickness": float(cloud_thickness),
                        "tk_cross": tk_bullish_cross,
                        "cloud_breakout": close_prev <= cloud_top,
                        "price": context.current_price,
                    },
                ))

        # SELL: Price breaks below cloud OR TK bearish cross below cloud
        elif price_below_cloud:
            if tk_bearish_cross or (close_prev >= cloud_bottom and close_current < cloud_bottom):
                strength = min(1.0, 0.5 + cloud_strength * 0.5)

                reason_parts = []
                if close_prev >= cloud_bottom and close_current < cloud_bottom:
                    reason_parts.append("price broke below cloud")
                if tk_bearish_cross:
                    reason_parts.append("Tenkan crossed below Kijun")

                signals.append(self.create_signal(
                    signal_type=SignalType.SELL,
                    instrument=context.instrument,
                    strength=strength,
                    reason=f"Ichimoku bearish: {', '.join(reason_parts)}",
                    metadata={
                        "close": float(close_current),
                        "tenkan": float(tenkan_current),
                        "kijun": float(kijun_current),
                        "senkou_a": float(senkou_a_current),
                        "senkou_b": float(senkou_b_current),
                        "cloud_top": float(cloud_top),
                        "cloud_bottom": float(cloud_bottom),
                        "cloud_thickness": float(cloud_thickness),
                        "tk_cross": tk_bearish_cross,
                        "cloud_breakout": close_prev >= cloud_bottom,
                        "price": context.current_price,
                    },
                ))

        return signals

    def validate(self) -> list[str]:
        """Validate strategy parameters."""
        errors = super().validate()

        tenkan = self.params.get("tenkan_period", 9)
        kijun = self.params.get("kijun_period", 26)
        senkou_b = self.params.get("senkou_b_period", 52)

        if tenkan >= kijun:
            errors.append("Tenkan period must be less than Kijun period")

        if kijun >= senkou_b:
            errors.append("Kijun period must be less than Senkou B period")

        if tenkan < 1:
            errors.append("Tenkan period must be at least 1")

        return errors
