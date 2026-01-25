"""Base class for technical indicators."""

from abc import ABC, abstractmethod
from typing import Any

import pandas as pd


class BaseIndicator(ABC):
    """
    Abstract base class for all technical indicators.

    To create a custom indicator:
    1. Subclass BaseIndicator
    2. Set name and default_params
    3. Implement calculate() method
    4. Register with IndicatorRegistry
    """

    name: str = "Base Indicator"
    description: str = ""
    default_params: dict[str, Any] = {}

    @abstractmethod
    def calculate(self, df: pd.DataFrame, **params: Any) -> pd.Series | pd.DataFrame:
        """
        Calculate indicator values from OHLCV DataFrame.

        Args:
            df: DataFrame with columns: open, high, low, close, volume
                Index should be datetime
            **params: Indicator-specific parameters

        Returns:
            Series for single-value indicators (e.g., RSI)
            DataFrame for multi-value indicators (e.g., MACD with signal and histogram)
        """
        pass

    def get_params(self, **overrides: Any) -> dict[str, Any]:
        """Get parameters with defaults and overrides merged."""
        params = self.default_params.copy()
        params.update(overrides)
        return params

    def validate_dataframe(self, df: pd.DataFrame) -> None:
        """Validate that DataFrame has required columns."""
        required = {"open", "high", "low", "close"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"DataFrame missing required columns: {missing}")

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}')"
