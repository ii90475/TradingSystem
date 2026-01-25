"""RSI Reversal Strategy.

A mean-reversion strategy that generates signals based on
RSI (Relative Strength Index) oversold and overbought conditions.

BUY: RSI drops below oversold level then rises back above it
SELL: RSI rises above overbought level then falls back below it
"""

import pandas as pd

from tradingsystem.models.signal import Signal, SignalType
from tradingsystem.strategies.base import BaseStrategy, IndicatorConfig, StrategyContext
from tradingsystem.strategies.registry import StrategyRegistry


@StrategyRegistry.register("rsi_reversal")
class RSIReversalStrategy(BaseStrategy):
    """
    RSI Reversal (Mean Reversion) Strategy.

    Generates buy signals when RSI exits oversold territory,
    and sell signals when RSI exits overbought territory.

    Parameters:
        rsi_period: RSI calculation period (default: 14)
        oversold: Oversold threshold (default: 30)
        overbought: Overbought threshold (default: 70)
        confirmation_periods: Periods to confirm reversal (default: 1)
    """

    name = "RSI Reversal"
    description = "Mean-reversion strategy using RSI overbought/oversold reversals"
    version = "1.0.0"
    author = "TradingSystem"

    instruments = ["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD"]
    periods = ["M1", "M5", "15m", "1h"]

    default_params = {
        "rsi_period": 14,
        "oversold": 30,
        "overbought": 70,
        "confirmation_periods": 1,
    }

    @property
    def required_indicators(self) -> list[IndicatorConfig]:
        """Dynamic indicator config based on parameters."""
        rsi_period = self.params.get("rsi_period", 14)

        return [
            IndicatorConfig(
                indicator_type="rsi",
                params={"length": rsi_period},
                column_name="rsi",
            ),
        ]

    def generate_signals(self, context: StrategyContext) -> list[Signal]:
        """
        Generate RSI reversal signals.

        Looks for RSI exiting oversold/overbought zones.
        """
        signals = []

        # Get RSI values
        rsi = context.indicators.get("rsi")
        if rsi is None:
            return signals

        # Need enough data points
        confirmation = self.params.get("confirmation_periods", 1)
        min_periods = confirmation + 2

        if len(rsi) < min_periods:
            return signals

        # Get threshold values
        oversold = self.params.get("oversold", 30)
        overbought = self.params.get("overbought", 70)

        # Get recent RSI values
        rsi_current = rsi.iloc[-1]
        rsi_prev = rsi.iloc[-2]

        # Skip if values are NaN
        if pd.isna(rsi_current) or pd.isna(rsi_prev):
            return signals

        # Check for oversold reversal (BUY signal)
        # RSI was below oversold, now crossing above
        if rsi_prev <= oversold and rsi_current > oversold:
            # Calculate strength based on how oversold it was
            min_rsi = rsi.iloc[-(confirmation + 2):-1].min()
            if pd.notna(min_rsi):
                # Lower RSI = stronger reversal signal
                strength = min(1.0, (oversold - min_rsi) / oversold)

                signals.append(self.create_signal(
                    signal_type=SignalType.BUY,
                    instrument=context.instrument,
                    strength=max(0.3, strength),  # Minimum strength of 0.3
                    reason=f"RSI reversal from oversold: RSI crossed above {oversold} (was {min_rsi:.1f})",
                    metadata={
                        "rsi": float(rsi_current),
                        "rsi_min": float(min_rsi),
                        "oversold_level": oversold,
                        "reversal_type": "oversold",
                        "price": context.current_price,
                    },
                ))

        # Check for overbought reversal (SELL signal)
        # RSI was above overbought, now crossing below
        elif rsi_prev >= overbought and rsi_current < overbought:
            # Calculate strength based on how overbought it was
            max_rsi = rsi.iloc[-(confirmation + 2):-1].max()
            if pd.notna(max_rsi):
                # Higher RSI = stronger reversal signal
                strength = min(1.0, (max_rsi - overbought) / (100 - overbought))

                signals.append(self.create_signal(
                    signal_type=SignalType.SELL,
                    instrument=context.instrument,
                    strength=max(0.3, strength),
                    reason=f"RSI reversal from overbought: RSI crossed below {overbought} (was {max_rsi:.1f})",
                    metadata={
                        "rsi": float(rsi_current),
                        "rsi_max": float(max_rsi),
                        "overbought_level": overbought,
                        "reversal_type": "overbought",
                        "price": context.current_price,
                    },
                ))

        return signals

    def validate(self) -> list[str]:
        """Validate strategy parameters."""
        errors = super().validate()

        oversold = self.params.get("oversold", 30)
        overbought = self.params.get("overbought", 70)

        if oversold >= overbought:
            errors.append("Oversold level must be less than overbought level")

        if oversold < 0 or oversold > 50:
            errors.append("Oversold level should be between 0 and 50")

        if overbought < 50 or overbought > 100:
            errors.append("Overbought level should be between 50 and 100")

        return errors
