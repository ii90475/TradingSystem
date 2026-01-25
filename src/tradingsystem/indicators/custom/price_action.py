"""Price action indicators."""

from typing import Any

import pandas as pd

from tradingsystem.indicators.base import BaseIndicator
from tradingsystem.indicators.registry import IndicatorRegistry


@IndicatorRegistry.register("price_change")
class PriceChange(BaseIndicator):
    """
    Simple price change indicator.

    Calculates the absolute and percentage price change over a period.
    """

    name = "Price Change"
    description = "Absolute and percentage price change"
    default_params = {"period": 1}

    def calculate(
        self,
        df: pd.DataFrame,
        period: int = 1,
        **kwargs: Any,
    ) -> pd.DataFrame:
        """
        Calculate price change.

        Args:
            df: OHLCV DataFrame
            period: Number of periods to look back

        Returns:
            DataFrame with 'change' and 'change_pct' columns
        """
        self.validate_dataframe(df)

        change = df["close"].diff(periods=period)
        change_pct = df["close"].pct_change(periods=period) * 100

        return pd.DataFrame({
            "change": change,
            "change_pct": change_pct,
        }, index=df.index)


@IndicatorRegistry.register("hl_range")
class HighLowRange(BaseIndicator):
    """
    High-Low range indicator.

    Measures the trading range as a percentage of the close price.
    Useful for volatility analysis.
    """

    name = "High-Low Range"
    description = "Trading range as percentage of close"
    default_params = {"period": 1}

    def calculate(
        self,
        df: pd.DataFrame,
        period: int = 1,
        **kwargs: Any,
    ) -> pd.DataFrame:
        """
        Calculate high-low range.

        Args:
            df: OHLCV DataFrame
            period: Rolling period for range calculation

        Returns:
            DataFrame with 'range' (absolute) and 'range_pct' (percentage)
        """
        self.validate_dataframe(df)

        if period == 1:
            # Single candle range
            range_abs = df["high"] - df["low"]
        else:
            # Rolling range over period
            range_abs = df["high"].rolling(period).max() - df["low"].rolling(period).min()

        range_pct = (range_abs / df["close"]) * 100

        return pd.DataFrame({
            "range": range_abs,
            "range_pct": range_pct,
        }, index=df.index)
