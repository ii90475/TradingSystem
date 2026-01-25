"""Technical indicators module.

Provides:
- Base class for custom indicators
- Registry for indicator management
- pandas-ta integration for 150+ indicators
- Custom indicator examples
"""

from tradingsystem.indicators.base import BaseIndicator
from tradingsystem.indicators.registry import IndicatorRegistry
from tradingsystem.indicators.pandas_ta_wrapper import (
    ensure_initialized,
    register_pandas_ta_indicators,
    calculate_pandas_ta_indicator,
    sma,
    ema,
    rsi,
    macd,
    bbands,
    atr,
    stoch,
)

# Import custom indicators to trigger registration
from tradingsystem.indicators import custom

__all__ = [
    # Base classes
    "BaseIndicator",
    "IndicatorRegistry",
    # pandas-ta functions
    "ensure_initialized",
    "register_pandas_ta_indicators",
    "calculate_pandas_ta_indicator",
    # Convenience functions
    "sma",
    "ema",
    "rsi",
    "macd",
    "bbands",
    "atr",
    "stoch",
]
