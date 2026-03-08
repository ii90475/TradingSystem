"""Tests for strategy generator service."""

import pytest

from tradingsystem.services.strategy_generator_service import (
    validate_strategy_code,
    _extract_strategy_id,
    _extract_class_name,
    _load_strategy_from_code,
)
from tradingsystem.strategies.base import BaseStrategy
from tradingsystem.strategies.registry import StrategyRegistry


VALID_CODE = '''import pandas as pd

from tradingsystem.models.signal import Signal, SignalType
from tradingsystem.strategies.base import BaseStrategy, IndicatorConfig, StrategyContext
from tradingsystem.strategies.registry import StrategyRegistry


@StrategyRegistry.register("test_strat")
class TestStrategy(BaseStrategy):
    name = "Test Strategy"
    description = "A test strategy"
    version = "1.0.0"
    author = "Generated"
    instruments = ["EUR_USD"]
    periods = ["H1"]
    default_params = {"period": 14}

    @property
    def required_indicators(self) -> list[IndicatorConfig]:
        return [IndicatorConfig(indicator_type="rsi", params={"length": 14}, column_name="rsi")]

    def generate_signals(self, context: StrategyContext) -> list[Signal]:
        return []
'''


class TestExtractStrategyId:
    def test_extracts_id(self):
        assert _extract_strategy_id(VALID_CODE) == "test_strat"

    def test_returns_none_for_missing(self):
        assert _extract_strategy_id("class Foo(BaseStrategy): pass") is None


class TestExtractClassName:
    def test_extracts_class(self):
        assert _extract_class_name(VALID_CODE) == "TestStrategy"

    def test_returns_none_for_missing(self):
        assert _extract_class_name("# no class here") is None


class TestValidateStrategyCode:
    def test_valid_code_passes(self):
        errors = validate_strategy_code(VALID_CODE)
        assert errors == []

    def test_syntax_error(self):
        errors = validate_strategy_code("def foo(:\n  pass")
        assert any("Syntax error" in e for e in errors)

    def test_missing_base_import(self):
        code = VALID_CODE.replace(
            "from tradingsystem.strategies.base import BaseStrategy, IndicatorConfig, StrategyContext\n", ""
        )
        errors = validate_strategy_code(code)
        assert any("Missing BaseStrategy import" in e for e in errors)

    def test_missing_registry_import(self):
        code = VALID_CODE.replace("from tradingsystem.strategies.registry import StrategyRegistry", "")
        errors = validate_strategy_code(code)
        assert any("Missing StrategyRegistry import" in e for e in errors)

    def test_missing_signal_import(self):
        code = VALID_CODE.replace("from tradingsystem.models.signal import Signal, SignalType", "")
        errors = validate_strategy_code(code)
        assert any("Missing Signal" in e for e in errors)

    def test_missing_decorator(self):
        code = VALID_CODE.replace('@StrategyRegistry.register("test_strat")\n', "")
        errors = validate_strategy_code(code)
        assert any("decorator" in e.lower() for e in errors)

    def test_missing_generate_signals(self):
        code = VALID_CODE.replace("def generate_signals", "def _generate_signals")
        errors = validate_strategy_code(code)
        assert any("generate_signals" in e for e in errors)

    def test_missing_required_indicators(self):
        code = VALID_CODE.replace("required_indicators", "other_indicators")
        errors = validate_strategy_code(code)
        assert any("required_indicators" in e for e in errors)

    def test_blocks_os_import(self):
        code = "import os\n" + VALID_CODE
        errors = validate_strategy_code(code)
        assert any("Disallowed" in e for e in errors)

    def test_blocks_subprocess_import(self):
        code = "import subprocess\n" + VALID_CODE
        errors = validate_strategy_code(code)
        assert any("Disallowed" in e for e in errors)

    def test_blocks_eval(self):
        code = VALID_CODE.replace("return []", "return eval('[]')")
        errors = validate_strategy_code(code)
        assert any("Disallowed" in e for e in errors)

    def test_blocks_exec(self):
        code = VALID_CODE.replace("return []", "exec('pass')\n        return []")
        errors = validate_strategy_code(code)
        assert any("Disallowed" in e for e in errors)

    def test_blocks_open(self):
        code = VALID_CODE.replace("return []", "open('/etc/passwd')\n        return []")
        errors = validate_strategy_code(code)
        assert any("Disallowed" in e for e in errors)

    def test_blocks_arbitrary_imports(self):
        code = "import requests\n" + VALID_CODE
        errors = validate_strategy_code(code)
        assert any("Disallowed import" in e for e in errors)


class TestLoadStrategyFromCode:
    """Tests for _load_strategy_from_code function."""

    def test_loads_valid_strategy(self):
        """Should load a strategy instance from code."""
        instance = _load_strategy_from_code(VALID_CODE)
        assert isinstance(instance, BaseStrategy)
        assert instance.name == "Test Strategy"
        assert instance.author == "Generated"

    def test_does_not_register_in_registry(self):
        """Should NOT register the strategy in StrategyRegistry."""
        was_registered_before = StrategyRegistry.is_registered("test_strat")
        _load_strategy_from_code(VALID_CODE)
        # If it wasn't registered before, it shouldn't be now
        if not was_registered_before:
            assert not StrategyRegistry.is_registered("test_strat")

    def test_raises_on_missing_strategy_id(self):
        """Should raise ValueError when code has no register decorator."""
        code = VALID_CODE.replace('@StrategyRegistry.register("test_strat")\n', "")
        with pytest.raises(ValueError, match="Cannot extract strategy_id"):
            _load_strategy_from_code(code)

    def test_raises_on_invalid_code(self):
        """Should raise on code that can't be loaded."""
        code = VALID_CODE.replace("class TestStrategy", "class 123Invalid")
        with pytest.raises((ValueError, SyntaxError)):
            _load_strategy_from_code(code)
