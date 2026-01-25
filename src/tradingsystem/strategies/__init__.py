"""Trading strategies module.

Provides:
- Base class for custom strategies
- Strategy registry for discovery and management
- Built-in example strategies
"""

from tradingsystem.strategies.base import (
    BaseStrategy,
    IndicatorConfig,
    StrategyContext,
)
from tradingsystem.strategies.registry import (
    StrategyRegistry,
    discover_builtin_strategies,
)

__all__ = [
    "BaseStrategy",
    "IndicatorConfig",
    "StrategyContext",
    "StrategyRegistry",
    "discover_builtin_strategies",
]
