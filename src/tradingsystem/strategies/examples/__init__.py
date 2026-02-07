"""Built-in example trading strategies."""

from tradingsystem.strategies.examples.atr_trailing import ATRTrailingStrategy
from tradingsystem.strategies.examples.bollinger_breakout import BollingerBreakoutStrategy
from tradingsystem.strategies.examples.ichimoku_cloud import IchimokuCloudStrategy
from tradingsystem.strategies.examples.ma_crossover import MACrossoverStrategy
from tradingsystem.strategies.examples.macd_divergence import MACDDivergenceStrategy
from tradingsystem.strategies.examples.multi_timeframe import MultiTimeframeStrategy
from tradingsystem.strategies.examples.rsi_reversal import RSIReversalStrategy
from tradingsystem.strategies.examples.support_resistance import SupportResistanceStrategy

__all__ = [
    "ATRTrailingStrategy",
    "BollingerBreakoutStrategy",
    "IchimokuCloudStrategy",
    "MACrossoverStrategy",
    "MACDDivergenceStrategy",
    "MultiTimeframeStrategy",
    "RSIReversalStrategy",
    "SupportResistanceStrategy",
]
