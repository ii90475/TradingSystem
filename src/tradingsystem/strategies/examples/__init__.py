"""Built-in example trading strategies."""

from tradingsystem.strategies.examples.ma_crossover import MACrossoverStrategy
from tradingsystem.strategies.examples.rsi_reversal import RSIReversalStrategy

__all__ = [
    "MACrossoverStrategy",
    "RSIReversalStrategy",
]
