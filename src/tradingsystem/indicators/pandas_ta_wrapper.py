"""Pandas-TA integration for 150+ technical indicators."""

import logging
from typing import Any

import pandas as pd
import pandas_ta as ta

from tradingsystem.indicators.registry import IndicatorRegistry

logger = logging.getLogger(__name__)

# Categories of pandas-ta indicators
INDICATOR_CATEGORIES = {
    "trend": [
        "sma", "ema", "wma", "hma", "tema", "dema", "kama", "zlma",
        "t3", "vidya", "fwma", "pwma", "swma", "alma", "linreg",
        "adx", "aroon", "cci", "cmo", "dpo", "psar", "supertrend",
    ],
    "momentum": [
        "rsi", "stoch", "stochrsi", "willr", "uo", "ao", "apo",
        "ppo", "macd", "tsi", "cfo", "cg", "coppock", "kst",
        "mom", "pgo", "roc", "rvgi", "slope", "squeeze",
    ],
    "volatility": [
        "atr", "natr", "bbands", "kc", "donchian", "hwc", "massi",
        "rvi", "thermo", "true_range", "ui",
    ],
    "volume": [
        "ad", "adosc", "aobv", "cmf", "efi", "eom", "kvo",
        "mfi", "nvi", "obv", "pvi", "pvol", "pvr", "pvt", "vp",
    ],
    "overlap": [
        "dema", "ema", "fwma", "hilo", "hl2", "hlc3", "hma",
        "ichimoku", "jma", "kama", "linreg", "mcgd", "midpoint",
        "midprice", "ohlc4", "pwma", "rma", "sinwma", "sma",
        "ssf", "supertrend", "swma", "t3", "tema", "trima",
        "vidya", "vwap", "vwma", "wcp", "wma", "zlma",
    ],
}


def register_pandas_ta_indicators() -> int:
    """
    Register all available pandas-ta indicators.

    Returns:
        Number of indicators registered
    """
    count = 0

    # Known indicator function names in pandas-ta (lowercase, callable)
    # These are the main indicator functions available via ta accessor
    for indicator_name in dir(ta):
        # Skip private/special methods and classes
        if indicator_name.startswith("_"):
            continue

        # Get the attribute
        func = getattr(ta, indicator_name, None)

        # Only register callable functions with lowercase names (indicators)
        # Skip uppercase names (classes) and non-callables
        if callable(func) and indicator_name[0].islower():
            try:
                # Try to get docstring for description
                description = ""
                if func.__doc__:
                    # Get first non-empty line
                    for line in func.__doc__.split("\n"):
                        line = line.strip()
                        if line:
                            description = line
                            break

                IndicatorRegistry.register_pandas_ta(
                    name=indicator_name,
                    func=func,
                    description=description[:200],  # Limit description length
                )
                count += 1
            except Exception as e:
                logger.debug(f"Skipped {indicator_name}: {e}")

    logger.info(f"Registered {count} pandas-ta indicators")
    return count


def calculate_pandas_ta_indicator(
    df: pd.DataFrame,
    indicator_name: str,
    **params: Any,
) -> pd.Series | pd.DataFrame | None:
    """
    Calculate a pandas-ta indicator on the given DataFrame.

    Args:
        df: OHLCV DataFrame with columns: open, high, low, close, volume
        indicator_name: Name of the indicator (e.g., "sma", "rsi", "macd")
        **params: Parameters for the indicator

    Returns:
        Series or DataFrame with indicator values, or None if calculation fails
    """
    indicator_info = IndicatorRegistry.get_pandas_ta(indicator_name)
    if not indicator_info:
        raise ValueError(f"Unknown pandas-ta indicator: {indicator_name}")

    func = indicator_info["func"]

    try:
        # pandas-ta can work directly on DataFrame with ta accessor
        # or we can call the function directly

        # Most pandas-ta functions expect specific column names
        # Ensure we have the right columns
        required_cols = {"open", "high", "low", "close"}
        if not required_cols.issubset(df.columns):
            raise ValueError(f"DataFrame must have columns: {required_cols}")

        # Call the indicator function
        result = func(
            high=df["high"],
            low=df["low"],
            close=df["close"],
            open_=df.get("open"),
            volume=df.get("volume"),
            **params,
        )

        return result

    except TypeError:
        # Some indicators have different signatures, try simpler call
        try:
            result = func(df["close"], **params)
            return result
        except Exception as e:
            logger.error(f"Failed to calculate {indicator_name}: {e}")
            return None

    except Exception as e:
        logger.error(f"Failed to calculate {indicator_name}: {e}")
        return None


def calculate_indicator_ta_method(
    df: pd.DataFrame,
    indicator_name: str,
    **params: Any,
) -> pd.DataFrame:
    """
    Calculate indicator using pandas-ta's DataFrame extension method.

    This is often the easiest way to use pandas-ta.

    Args:
        df: OHLCV DataFrame
        indicator_name: Indicator name
        **params: Indicator parameters

    Returns:
        DataFrame with original data plus indicator columns
    """
    # Make a copy to avoid modifying original
    df_copy = df.copy()

    # Use pandas-ta's ta accessor
    # This adds indicator columns to the DataFrame
    try:
        # Get the indicator method from ta accessor
        ta_method = getattr(df_copy.ta, indicator_name, None)
        if ta_method is None:
            raise ValueError(f"Unknown indicator: {indicator_name}")

        # Call the method with parameters
        result = ta_method(**params, append=True)

        # If append=True, columns are added to df_copy
        # If not, result contains the indicator values
        if result is not None:
            return result

        return df_copy

    except Exception as e:
        logger.error(f"Failed to calculate {indicator_name} via ta method: {e}")
        raise


# Common indicator shortcuts for convenience
def sma(df: pd.DataFrame, length: int = 20) -> pd.Series:
    """Simple Moving Average."""
    return df.ta.sma(length=length)


def ema(df: pd.DataFrame, length: int = 20) -> pd.Series:
    """Exponential Moving Average."""
    return df.ta.ema(length=length)


def rsi(df: pd.DataFrame, length: int = 14) -> pd.Series:
    """Relative Strength Index."""
    return df.ta.rsi(length=length)


def macd(
    df: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    """Moving Average Convergence Divergence."""
    return df.ta.macd(fast=fast, slow=slow, signal=signal)


def bbands(
    df: pd.DataFrame,
    length: int = 20,
    std: float = 2.0,
) -> pd.DataFrame:
    """Bollinger Bands."""
    return df.ta.bbands(length=length, std=std)


def atr(df: pd.DataFrame, length: int = 14) -> pd.Series:
    """Average True Range."""
    return df.ta.atr(length=length)


def stoch(
    df: pd.DataFrame,
    k: int = 14,
    d: int = 3,
    smooth_k: int = 3,
) -> pd.DataFrame:
    """Stochastic Oscillator."""
    return df.ta.stoch(k=k, d=d, smooth_k=smooth_k)


# Initialize pandas-ta indicators on module load
_initialized = False


def ensure_initialized() -> None:
    """Ensure pandas-ta indicators are registered."""
    global _initialized
    if not _initialized:
        register_pandas_ta_indicators()
        _initialized = True
