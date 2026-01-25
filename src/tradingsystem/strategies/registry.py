"""Strategy registry for discovering and managing trading strategies."""

import importlib
import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any

from tradingsystem.strategies.base import BaseStrategy

logger = logging.getLogger(__name__)


class StrategyRegistry:
    """
    Registry for discovering, loading, and managing trading strategies.

    Strategies can be registered in two ways:
    1. Decorator: @StrategyRegistry.register("my_strategy")
    2. Auto-discovery: Place strategy files in strategies/examples/ or user directory

    Example:
        @StrategyRegistry.register("ma_crossover")
        class MACrossoverStrategy(BaseStrategy):
            ...

        # Or auto-discover from directory
        StrategyRegistry.discover_strategies("/path/to/strategies")
    """

    _strategies: dict[str, type[BaseStrategy]] = {}
    _instances: dict[str, BaseStrategy] = {}

    @classmethod
    def register(cls, name: str):
        """
        Decorator to register a strategy class.

        Usage:
            @StrategyRegistry.register("my_strategy")
            class MyStrategy(BaseStrategy):
                ...
        """
        def decorator(strategy_cls: type[BaseStrategy]) -> type[BaseStrategy]:
            if not issubclass(strategy_cls, BaseStrategy):
                raise TypeError(f"{strategy_cls.__name__} must be a subclass of BaseStrategy")

            cls._strategies[name.lower()] = strategy_cls
            logger.debug(f"Registered strategy: {name}")
            return strategy_cls

        return decorator

    @classmethod
    def register_class(cls, name: str, strategy_cls: type[BaseStrategy]) -> None:
        """Register a strategy class directly (not as decorator)."""
        if not issubclass(strategy_cls, BaseStrategy):
            raise TypeError(f"{strategy_cls.__name__} must be a subclass of BaseStrategy")

        cls._strategies[name.lower()] = strategy_cls
        logger.debug(f"Registered strategy: {name}")

    @classmethod
    def get(cls, name: str) -> type[BaseStrategy] | None:
        """Get a strategy class by name."""
        return cls._strategies.get(name.lower())

    @classmethod
    def get_instance(cls, name: str, **params: Any) -> BaseStrategy | None:
        """
        Get or create a strategy instance.

        Args:
            name: Strategy name
            **params: Parameters to pass to strategy constructor

        Returns:
            Strategy instance or None if not found
        """
        name_lower = name.lower()
        strategy_cls = cls._strategies.get(name_lower)

        if not strategy_cls:
            return None

        # Create new instance with params
        instance = strategy_cls(**params)
        cls._instances[name_lower] = instance
        return instance

    @classmethod
    def get_running_instance(cls, name: str) -> BaseStrategy | None:
        """Get an existing running strategy instance."""
        return cls._instances.get(name.lower())

    @classmethod
    def list_strategies(cls) -> list[str]:
        """List all registered strategy names."""
        return list(cls._strategies.keys())

    @classmethod
    def list_all(cls) -> list[dict[str, Any]]:
        """List all registered strategies with their info."""
        result = []
        for name, strategy_cls in cls._strategies.items():
            try:
                # Create temporary instance to get info
                instance = strategy_cls()
                info = instance.get_info()
                info["id"] = name
                result.append(info)
            except Exception as e:
                logger.warning(f"Failed to get info for strategy {name}: {e}")
                result.append({
                    "id": name,
                    "name": strategy_cls.name if hasattr(strategy_cls, "name") else name,
                    "error": str(e),
                })
        return result

    @classmethod
    def is_registered(cls, name: str) -> bool:
        """Check if a strategy is registered."""
        return name.lower() in cls._strategies

    @classmethod
    def discover_strategies(cls, directory: str | Path) -> int:
        """
        Auto-discover and register strategies from a directory.

        Scans the directory for Python files and loads any classes
        that inherit from BaseStrategy.

        Args:
            directory: Path to directory containing strategy files

        Returns:
            Number of strategies discovered
        """
        directory = Path(directory)
        if not directory.exists():
            logger.warning(f"Strategy directory does not exist: {directory}")
            return 0

        count = 0
        for file_path in directory.glob("*.py"):
            if file_path.name.startswith("_"):
                continue

            try:
                strategies = cls._load_strategies_from_file(file_path)
                count += strategies
            except Exception as e:
                logger.error(f"Failed to load strategies from {file_path}: {e}")

        logger.info(f"Discovered {count} strategies from {directory}")
        return count

    @classmethod
    def _load_strategies_from_file(cls, file_path: Path) -> int:
        """Load strategy classes from a Python file."""
        module_name = f"tradingsystem.strategies.dynamic.{file_path.stem}"

        # Load the module
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            return 0

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module

        try:
            spec.loader.exec_module(module)
        except Exception as e:
            logger.error(f"Error executing module {file_path}: {e}")
            return 0

        # Find and register strategy classes
        count = 0
        for attr_name in dir(module):
            if attr_name.startswith("_"):
                continue

            attr = getattr(module, attr_name)

            # Check if it's a strategy class (not BaseStrategy itself)
            if (
                isinstance(attr, type)
                and issubclass(attr, BaseStrategy)
                and attr is not BaseStrategy
                and not cls.is_registered(attr_name.lower())
            ):
                # Use class name as strategy ID
                strategy_id = attr_name.lower()
                cls.register_class(strategy_id, attr)
                count += 1
                logger.debug(f"Auto-registered strategy: {strategy_id} from {file_path.name}")

        return count

    @classmethod
    def reload_strategy(cls, name: str, file_path: str | Path) -> bool:
        """
        Reload a strategy from file (for hot-reload during development).

        Args:
            name: Strategy name to reload
            file_path: Path to strategy file

        Returns:
            True if reload successful
        """
        name_lower = name.lower()

        # Remove existing registration
        if name_lower in cls._strategies:
            del cls._strategies[name_lower]

        # Remove any running instance
        if name_lower in cls._instances:
            instance = cls._instances[name_lower]
            if instance.is_running:
                instance.on_stop()
            del cls._instances[name_lower]

        # Reload from file
        try:
            count = cls._load_strategies_from_file(Path(file_path))
            return count > 0
        except Exception as e:
            logger.error(f"Failed to reload strategy {name}: {e}")
            return False

    @classmethod
    def clear(cls) -> None:
        """Clear all registered strategies (mainly for testing)."""
        # Stop any running instances
        for instance in cls._instances.values():
            if instance.is_running:
                instance.on_stop()

        cls._strategies.clear()
        cls._instances.clear()


def discover_builtin_strategies() -> int:
    """Discover strategies from the built-in examples directory."""
    examples_dir = Path(__file__).parent / "examples"
    return StrategyRegistry.discover_strategies(examples_dir)
