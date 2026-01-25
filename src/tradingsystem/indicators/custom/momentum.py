"""Custom momentum indicator example."""

from typing import Any

import pandas as pd

from tradingsystem.indicators.base import BaseIndicator
from tradingsystem.indicators.registry import IndicatorRegistry


@IndicatorRegistry.register("custom_momentum")
class CustomMomentum(BaseIndicator):
    """
    Custom momentum indicator.

    Calculates percentage price change over a specified period,
    normalized to a -100 to +100 scale for easy interpretation.

    Example usage:
        indicator = CustomMomentum()
        result = indicator.calculate(df, period=14)
    """

    name = "Custom Momentum"
    description = "Normalized momentum indicator (-100 to +100)"
    default_params = {"period": 14}

    def calculate(
        self,
        df: pd.DataFrame,
        period: int = 14,
        **kwargs: Any,
    ) -> pd.Series:
        """
        Calculate custom momentum.

        Args:
            df: OHLCV DataFrame with 'close' column
            period: Lookback period for momentum calculation

        Returns:
            Series with momentum values (-100 to +100)
        """
        self.validate_dataframe(df)

        # Calculate raw momentum (percentage change)
        momentum = df["close"].pct_change(periods=period) * 100

        # Normalize to -100 to +100 range using tanh-like scaling
        # This prevents extreme outliers from dominating
        normalized = momentum.clip(lower=-100, upper=100)

        return normalized
