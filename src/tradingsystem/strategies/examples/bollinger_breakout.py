"""Bollinger Band Breakout Strategy.

A volatility/mean-reversion strategy that generates signals when
price breaks out of Bollinger Bands and re-enters.

BUY: Price closes below lower band (oversold) then re-enters
SELL: Price closes above upper band (overbought) then re-enters
"""

import pandas as pd

from tradingsystem.models.signal import Signal, SignalType
from tradingsystem.strategies.base import BaseStrategy, IndicatorConfig, StrategyContext
from tradingsystem.strategies.registry import StrategyRegistry


@StrategyRegistry.register("bollinger_breakout")
class BollingerBreakoutStrategy(BaseStrategy):
    """
    Bollinger Band Breakout Strategy.

    Generates buy signals when price re-enters from below the lower band,
    and sell signals when price re-enters from above the upper band.
    Can also detect "squeeze" conditions for breakout anticipation.

    Parameters:
        bb_period: Bollinger Band period (default: 20)
        bb_std: Standard deviation multiplier (default: 2.0)
        squeeze_threshold: Band width % for squeeze detection (default: 0.02)
    """

    name = "Bollinger Breakout"
    description = "Volatility/mean-reversion strategy using Bollinger Band breakouts"
    version = "1.0.0"
    author = "TradingSystem"

    instruments = ["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD"]
    periods = ["M5", "M15", "1h", "4h"]

    default_params = {
        "bb_period": 20,
        "bb_std": 2.0,
        "squeeze_threshold": 0.02,  # 2% band width for squeeze
    }

    @property
    def required_indicators(self) -> list[IndicatorConfig]:
        """Dynamic indicator config based on parameters."""
        bb_period = self.params.get("bb_period", 20)
        bb_std = self.params.get("bb_std", 2.0)

        return [
            IndicatorConfig(
                indicator_type="bbands",
                params={"length": bb_period, "std": bb_std},
                column_name="bbands",
            ),
        ]

    def generate_signals(self, context: StrategyContext) -> list[Signal]:
        """
        Generate Bollinger Band breakout signals.

        Looks for price re-entering bands after breakout.
        """
        signals = []

        # Get Bollinger Band values
        bbands = context.indicators.get("bbands")
        if bbands is None:
            return signals

        # bbands returns DataFrame with upper, mid, lower columns
        if isinstance(bbands, pd.DataFrame):
            upper = bbands.get("upper")
            if upper is None:
                upper = bbands.get("BBU")
            mid = bbands.get("mid")
            if mid is None:
                mid = bbands.get("BBM")
            lower = bbands.get("lower")
            if lower is None:
                lower = bbands.get("BBL")
        else:
            # If passed as separate series in dict
            upper = context.indicators.get("bbands_upper")
            mid = context.indicators.get("bbands_mid")
            lower = context.indicators.get("bbands_lower")

        if upper is None or mid is None or lower is None:
            return signals

        # Need at least 2 data points to detect re-entry
        if len(upper) < 2 or len(context.candles) < 2:
            return signals

        # Get current and previous values
        close_current = context.candles["close"].iloc[-1]
        close_prev = context.candles["close"].iloc[-2]
        upper_current = upper.iloc[-1]
        upper_prev = upper.iloc[-2]
        lower_current = lower.iloc[-1]
        lower_prev = lower.iloc[-2]
        mid_current = mid.iloc[-1]

        # Skip if any values are NaN
        if pd.isna(close_current) or pd.isna(close_prev):
            return signals
        if pd.isna(upper_current) or pd.isna(lower_current) or pd.isna(mid_current):
            return signals
        if pd.isna(upper_prev) or pd.isna(lower_prev):
            return signals

        # Calculate band width for squeeze detection
        band_width = (upper_current - lower_current) / mid_current
        squeeze_threshold = self.params.get("squeeze_threshold", 0.02)
        is_squeeze = band_width < squeeze_threshold

        # Detect oversold re-entry (BUY signal)
        # Price was below lower band, now re-enters
        if close_prev < lower_prev and close_current >= lower_current:
            # Calculate signal strength based on how far below band price went
            overshoot = (lower_prev - close_prev) / lower_prev
            strength = min(1.0, 0.5 + overshoot * 10)  # Base 0.5, scale with overshoot

            signals.append(self.create_signal(
                signal_type=SignalType.BUY,
                instrument=context.instrument,
                strength=strength,
                reason=f"Bollinger oversold re-entry: price re-entered from below lower band",
                metadata={
                    "close": float(close_current),
                    "lower_band": float(lower_current),
                    "upper_band": float(upper_current),
                    "mid_band": float(mid_current),
                    "band_width": float(band_width),
                    "is_squeeze": is_squeeze,
                    "breakout_type": "oversold_reentry",
                    "price": context.current_price,
                },
            ))

        # Detect overbought re-entry (SELL signal)
        # Price was above upper band, now re-enters
        elif close_prev > upper_prev and close_current <= upper_current:
            # Calculate signal strength based on how far above band price went
            overshoot = (close_prev - upper_prev) / upper_prev
            strength = min(1.0, 0.5 + overshoot * 10)

            signals.append(self.create_signal(
                signal_type=SignalType.SELL,
                instrument=context.instrument,
                strength=strength,
                reason=f"Bollinger overbought re-entry: price re-entered from above upper band",
                metadata={
                    "close": float(close_current),
                    "lower_band": float(lower_current),
                    "upper_band": float(upper_current),
                    "mid_band": float(mid_current),
                    "band_width": float(band_width),
                    "is_squeeze": is_squeeze,
                    "breakout_type": "overbought_reentry",
                    "price": context.current_price,
                },
            ))

        return signals

    def validate(self) -> list[str]:
        """Validate strategy parameters."""
        errors = super().validate()

        bb_period = self.params.get("bb_period", 20)
        bb_std = self.params.get("bb_std", 2.0)
        squeeze_threshold = self.params.get("squeeze_threshold", 0.02)

        if bb_period < 5:
            errors.append("Bollinger Band period must be at least 5")

        if bb_std <= 0:
            errors.append("Standard deviation multiplier must be positive")

        if squeeze_threshold <= 0 or squeeze_threshold > 0.5:
            errors.append("Squeeze threshold must be between 0 and 0.5")

        return errors
