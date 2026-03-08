"""Tests for strategy generate/save API endpoints."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from tradingsystem.api.strategies import generate_strategy, save_strategy
from tradingsystem.api.strategies import GenerateStrategyRequest, SaveStrategyRequest


VALID_CODE = '''import pandas as pd

from tradingsystem.models.signal import Signal, SignalType
from tradingsystem.strategies.base import BaseStrategy, IndicatorConfig, StrategyContext
from tradingsystem.strategies.registry import StrategyRegistry


@StrategyRegistry.register("generated_test")
class GeneratedTestStrategy(BaseStrategy):
    name = "Generated Test"
    description = "A test strategy"
    version = "1.0.0"
    author = "Generated"
    instruments = ["EUR_USD"]
    periods = ["H1"]
    default_params = {}

    @property
    def required_indicators(self) -> list[IndicatorConfig]:
        return [IndicatorConfig(indicator_type="rsi", params={"length": 14}, column_name="rsi")]

    def generate_signals(self, context: StrategyContext) -> list[Signal]:
        return []
'''


class TestGenerateStrategy:
    @pytest.mark.asyncio
    async def test_generates_strategy(self):
        """Should return generated code."""
        mock_result = {
            "code": VALID_CODE,
            "strategy_id": "generated_test",
            "class_name": "GeneratedTestStrategy",
            "validation_errors": [],
        }
        with patch(
            "tradingsystem.api.strategies.strategy_generator_service"
        ) as mock_service:
            mock_service.generate_strategy = AsyncMock(return_value=mock_result)

            request = GenerateStrategyRequest(description="Buy when RSI is below 30")
            result = await generate_strategy(request)

            assert result["strategy_id"] == "generated_test"
            assert result["validation_errors"] == []

    @pytest.mark.asyncio
    async def test_returns_400_on_value_error(self):
        """Should return 400 when API key missing."""
        with patch(
            "tradingsystem.api.strategies.strategy_generator_service"
        ) as mock_service:
            mock_service.generate_strategy = AsyncMock(
                side_effect=ValueError("ANTHROPIC_API_KEY is not configured")
            )

            request = GenerateStrategyRequest(description="Buy when RSI is below 30")
            with pytest.raises(HTTPException) as exc:
                await generate_strategy(request)

            assert exc.value.status_code == 400


class TestSaveStrategy:
    @pytest.mark.asyncio
    async def test_saves_strategy(self):
        """Should save and register strategy."""
        mock_result = {
            "strategy_id": "generated_test",
            "file_path": "/path/to/generated_test.py",
            "registered": True,
        }
        with patch(
            "tradingsystem.api.strategies.strategy_generator_service"
        ) as mock_service:
            mock_service.save_strategy.return_value = mock_result

            request = SaveStrategyRequest(code=VALID_CODE)
            result = await save_strategy(request)

            assert result["strategy_id"] == "generated_test"
            assert result["registered"] is True

    @pytest.mark.asyncio
    async def test_returns_400_on_validation_failure(self):
        """Should return 400 when code fails validation."""
        with patch(
            "tradingsystem.api.strategies.strategy_generator_service"
        ) as mock_service:
            mock_service.save_strategy.side_effect = ValueError("Validation failed")

            request = SaveStrategyRequest(code=VALID_CODE)
            with pytest.raises(HTTPException) as exc:
                await save_strategy(request)

            assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_returns_400_on_duplicate(self):
        """Should return 400 when strategy already exists."""
        with patch(
            "tradingsystem.api.strategies.strategy_generator_service"
        ) as mock_service:
            mock_service.save_strategy.side_effect = ValueError(
                "Strategy 'generated_test' already exists"
            )

            request = SaveStrategyRequest(code=VALID_CODE)
            with pytest.raises(HTTPException) as exc:
                await save_strategy(request)

            assert exc.value.status_code == 400
