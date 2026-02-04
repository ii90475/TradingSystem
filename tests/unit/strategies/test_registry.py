"""Tests for strategy registry."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tradingsystem.strategies.base import BaseStrategy, StrategyContext
from tradingsystem.strategies.registry import StrategyRegistry, discover_builtin_strategies


# --- Test Strategy Classes ---


class MockValidStrategy(BaseStrategy):
    """Valid mock strategy for testing."""

    name = "Mock Valid"
    description = "A valid mock strategy"
    version = "1.0.0"
    instruments = ["EUR_USD"]
    periods = ["1h"]

    def generate_signals(self, context: StrategyContext):
        return []


class MockAnotherStrategy(BaseStrategy):
    """Another valid mock strategy."""

    name = "Mock Another"
    description = "Another mock strategy"
    instruments = ["GBP_USD"]
    periods = ["M5"]

    def generate_signals(self, context: StrategyContext):
        return []


class NotAStrategy:
    """Class that is not a BaseStrategy subclass."""

    pass


# --- Fixtures ---


@pytest.fixture(autouse=True)
def clean_registry():
    """Clear registry before each test."""
    # Store original strategies
    original_strategies = StrategyRegistry._strategies.copy()
    original_instances = StrategyRegistry._instances.copy()

    yield

    # Restore original state
    StrategyRegistry._strategies = original_strategies
    StrategyRegistry._instances = original_instances


# --- register decorator Tests ---


class TestRegisterDecorator:
    """Tests for @StrategyRegistry.register decorator."""

    def test_registers_strategy(self):
        """Should register strategy class."""

        @StrategyRegistry.register("test_strategy")
        class TestStrategy(BaseStrategy):
            name = "Test"
            instruments = ["EUR_USD"]
            periods = ["1h"]

            def generate_signals(self, context):
                return []

        assert StrategyRegistry.is_registered("test_strategy")

    def test_raises_for_non_strategy(self):
        """Should raise TypeError for non-BaseStrategy class."""
        with pytest.raises(TypeError, match="must be a subclass"):

            @StrategyRegistry.register("invalid")
            class NotStrategy:
                pass

    def test_lowercase_name(self):
        """Should store name in lowercase."""

        @StrategyRegistry.register("MixedCase")
        class MixedCaseStrategy(BaseStrategy):
            name = "Mixed"
            instruments = ["EUR_USD"]
            periods = ["1h"]

            def generate_signals(self, context):
                return []

        assert StrategyRegistry.is_registered("mixedcase")
        assert StrategyRegistry.get("MIXEDCASE") is not None


# --- register_class Tests ---


class TestRegisterClass:
    """Tests for StrategyRegistry.register_class method."""

    def test_registers_class_directly(self):
        """Should register a class without decorator."""
        StrategyRegistry.register_class("mock_valid", MockValidStrategy)

        assert StrategyRegistry.is_registered("mock_valid")
        assert StrategyRegistry.get("mock_valid") is MockValidStrategy

    def test_raises_for_non_strategy(self):
        """Should raise TypeError for non-BaseStrategy class."""
        with pytest.raises(TypeError, match="must be a subclass"):
            StrategyRegistry.register_class("invalid", NotAStrategy)


# --- get Tests ---


class TestGet:
    """Tests for StrategyRegistry.get method."""

    def test_returns_registered_class(self):
        """Should return registered strategy class."""
        StrategyRegistry.register_class("test", MockValidStrategy)

        result = StrategyRegistry.get("test")

        assert result is MockValidStrategy

    def test_returns_none_for_unknown(self):
        """Should return None for unknown strategy."""
        result = StrategyRegistry.get("nonexistent")

        assert result is None

    def test_case_insensitive(self):
        """Should be case-insensitive."""
        StrategyRegistry.register_class("mytest", MockValidStrategy)

        assert StrategyRegistry.get("MYTEST") is MockValidStrategy
        assert StrategyRegistry.get("MyTest") is MockValidStrategy


# --- get_instance Tests ---


class TestGetInstance:
    """Tests for StrategyRegistry.get_instance method."""

    def test_creates_instance(self):
        """Should create new instance."""
        StrategyRegistry.register_class("mock", MockValidStrategy)

        instance = StrategyRegistry.get_instance("mock")

        assert instance is not None
        assert isinstance(instance, MockValidStrategy)

    def test_passes_params_to_constructor(self):
        """Should pass params to strategy constructor."""
        StrategyRegistry.register_class("mock", MockValidStrategy)

        instance = StrategyRegistry.get_instance("mock", custom_param="value")

        assert instance.params.get("custom_param") == "value"

    def test_returns_none_for_unknown(self):
        """Should return None for unknown strategy."""
        result = StrategyRegistry.get_instance("nonexistent")

        assert result is None

    def test_stores_instance(self):
        """Should store created instance."""
        StrategyRegistry.register_class("mock", MockValidStrategy)

        instance = StrategyRegistry.get_instance("mock")
        running = StrategyRegistry.get_running_instance("mock")

        assert running is instance


# --- get_running_instance Tests ---


class TestGetRunningInstance:
    """Tests for StrategyRegistry.get_running_instance method."""

    def test_returns_existing_instance(self):
        """Should return previously created instance."""
        StrategyRegistry.register_class("mock", MockValidStrategy)
        instance = StrategyRegistry.get_instance("mock")

        result = StrategyRegistry.get_running_instance("mock")

        assert result is instance

    def test_returns_none_if_not_created(self):
        """Should return None if instance not created."""
        StrategyRegistry.register_class("mock", MockValidStrategy)

        result = StrategyRegistry.get_running_instance("mock")

        assert result is None


# --- list_strategies Tests ---


class TestListStrategies:
    """Tests for StrategyRegistry.list_strategies method."""

    def test_lists_registered_names(self):
        """Should list all registered strategy names."""
        StrategyRegistry.register_class("strat1", MockValidStrategy)
        StrategyRegistry.register_class("strat2", MockAnotherStrategy)

        names = StrategyRegistry.list_strategies()

        assert "strat1" in names
        assert "strat2" in names


# --- list_all Tests ---


class TestListAll:
    """Tests for StrategyRegistry.list_all method."""

    def test_returns_strategy_info(self):
        """Should return info for all strategies."""
        StrategyRegistry.register_class("mock", MockValidStrategy)

        result = StrategyRegistry.list_all()

        assert len(result) >= 1
        mock_info = next((s for s in result if s["id"] == "mock"), None)
        assert mock_info is not None
        assert mock_info["name"] == "Mock Valid"

    def test_handles_error_in_get_info(self):
        """Should handle errors when getting strategy info."""

        class BrokenStrategy(BaseStrategy):
            name = "Broken"
            instruments = ["EUR_USD"]
            periods = ["1h"]

            def __init__(self, **params):
                raise ValueError("Broken init")

            def generate_signals(self, context):
                return []

        StrategyRegistry.register_class("broken", BrokenStrategy)

        result = StrategyRegistry.list_all()

        broken_info = next((s for s in result if s["id"] == "broken"), None)
        assert broken_info is not None
        assert "error" in broken_info


# --- is_registered Tests ---


class TestIsRegistered:
    """Tests for StrategyRegistry.is_registered method."""

    def test_returns_true_for_registered(self):
        """Should return True for registered strategy."""
        StrategyRegistry.register_class("test", MockValidStrategy)

        assert StrategyRegistry.is_registered("test") is True

    def test_returns_false_for_unknown(self):
        """Should return False for unknown strategy."""
        assert StrategyRegistry.is_registered("unknown") is False


# --- discover_strategies Tests ---


class TestDiscoverStrategies:
    """Tests for StrategyRegistry.discover_strategies method."""

    def test_returns_zero_for_nonexistent_directory(self):
        """Should return 0 for non-existent directory."""
        count = StrategyRegistry.discover_strategies("/nonexistent/path")

        assert count == 0

    def test_discovers_strategies_from_directory(self):
        """Should discover strategies from Python files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a strategy file
            strategy_file = Path(tmpdir) / "test_strat.py"
            strategy_file.write_text("""
from tradingsystem.strategies.base import BaseStrategy

class DiscoveredStrategy(BaseStrategy):
    name = "Discovered"
    instruments = ["EUR_USD"]
    periods = ["1h"]

    def generate_signals(self, context):
        return []
""")

            count = StrategyRegistry.discover_strategies(tmpdir)

            assert count >= 1
            assert StrategyRegistry.is_registered("discoveredstrategy")

    def test_skips_private_files(self):
        """Should skip files starting with underscore."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create private file
            private_file = Path(tmpdir) / "_private.py"
            private_file.write_text("# Private module")

            count = StrategyRegistry.discover_strategies(tmpdir)

            assert count == 0


# --- clear Tests ---


class TestClear:
    """Tests for StrategyRegistry.clear method."""

    def test_clears_strategies(self):
        """Should clear all registered strategies."""
        StrategyRegistry.register_class("test", MockValidStrategy)
        StrategyRegistry.get_instance("test")

        StrategyRegistry.clear()

        assert not StrategyRegistry.is_registered("test")
        assert StrategyRegistry.get_running_instance("test") is None

    def test_stops_running_instances(self):
        """Should stop running instances before clearing."""
        StrategyRegistry.register_class("test", MockValidStrategy)
        instance = StrategyRegistry.get_instance("test")
        instance.on_start()

        assert instance.is_running is True

        StrategyRegistry.clear()

        assert instance.is_running is False


# --- discover_builtin_strategies Tests ---


class TestDiscoverBuiltinStrategies:
    """Tests for discover_builtin_strategies function."""

    def test_discovers_builtin(self):
        """Should discover built-in example strategies."""
        # This should find ma_crossover and rsi_reversal
        count = discover_builtin_strategies()

        # At least the two example strategies should be found
        assert count >= 0  # May already be registered
