"""Indicator registry for managing available indicators."""

import logging
from typing import Any, Callable

from tradingsystem.indicators.base import BaseIndicator

logger = logging.getLogger(__name__)


class IndicatorRegistry:
    """
    Registry for technical indicators.

    Supports both custom indicators (subclasses of BaseIndicator)
    and pandas-ta indicators (registered as wrappers).
    """

    _indicators: dict[str, type[BaseIndicator]] = {}
    _pandas_ta_indicators: dict[str, Callable] = {}

    @classmethod
    def register(cls, name: str) -> Callable[[type[BaseIndicator]], type[BaseIndicator]]:
        """
        Decorator to register a custom indicator.

        Usage:
            @IndicatorRegistry.register("my_indicator")
            class MyIndicator(BaseIndicator):
                ...
        """
        def decorator(indicator_cls: type[BaseIndicator]) -> type[BaseIndicator]:
            cls._indicators[name.lower()] = indicator_cls
            logger.debug(f"Registered custom indicator: {name}")
            return indicator_cls
        return decorator

    @classmethod
    def register_pandas_ta(cls, name: str, func: Callable, description: str = "") -> None:
        """
        Register a pandas-ta indicator function.

        Args:
            name: Indicator name (e.g., "sma", "rsi")
            func: The pandas-ta function
            description: Optional description
        """
        cls._pandas_ta_indicators[name.lower()] = {
            "func": func,
            "description": description,
        }
        logger.debug(f"Registered pandas-ta indicator: {name}")

    @classmethod
    def get(cls, name: str) -> type[BaseIndicator] | None:
        """Get a custom indicator class by name."""
        return cls._indicators.get(name.lower())

    @classmethod
    def get_pandas_ta(cls, name: str) -> dict | None:
        """Get a pandas-ta indicator by name."""
        return cls._pandas_ta_indicators.get(name.lower())

    @classmethod
    def is_registered(cls, name: str) -> bool:
        """Check if an indicator is registered (custom or pandas-ta)."""
        name_lower = name.lower()
        return name_lower in cls._indicators or name_lower in cls._pandas_ta_indicators

    @classmethod
    def list_custom(cls) -> list[str]:
        """List all registered custom indicator names."""
        return list(cls._indicators.keys())

    @classmethod
    def list_pandas_ta(cls) -> list[str]:
        """List all registered pandas-ta indicator names."""
        return list(cls._pandas_ta_indicators.keys())

    @classmethod
    def list_all(cls) -> dict[str, list[str]]:
        """List all registered indicators by type."""
        return {
            "custom": cls.list_custom(),
            "pandas_ta": cls.list_pandas_ta(),
        }

    @classmethod
    def get_info(cls, name: str) -> dict[str, Any] | None:
        """Get information about an indicator."""
        name_lower = name.lower()

        # Check custom indicators
        if name_lower in cls._indicators:
            indicator_cls = cls._indicators[name_lower]
            return {
                "name": name_lower,
                "type": "custom",
                "class": indicator_cls.__name__,
                "description": indicator_cls.description,
                "default_params": indicator_cls.default_params,
            }

        # Check pandas-ta indicators
        if name_lower in cls._pandas_ta_indicators:
            info = cls._pandas_ta_indicators[name_lower]
            return {
                "name": name_lower,
                "type": "pandas_ta",
                "description": info.get("description", ""),
            }

        return None

    @classmethod
    def clear(cls) -> None:
        """Clear all registered indicators (mainly for testing)."""
        cls._indicators.clear()
        cls._pandas_ta_indicators.clear()
