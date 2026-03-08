"""Unit tests for the Strategy Service."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pandas as pd
import pytest

from tradingsystem.models.signal import Signal, SignalType
from tradingsystem.strategies.base import BaseStrategy, IndicatorConfig, StrategyContext
from tradingsystem.services import strategy_service


class MockStrategy(BaseStrategy):
    """Mock strategy for testing."""

    name = "mock_strategy"
    description = "A mock strategy for testing"
    version = "1.0.0"
    instruments = ["EUR_USD", "GBP_USD"]
    periods = ["M1", "M5"]
    required_indicators = [
        IndicatorConfig("sma", {"length": 20}),
    ]
    default_params = {"threshold": 0.5}

    def generate_signals(self, context: StrategyContext) -> list[Signal]:
        """Generate a test signal."""
        return [
            self.create_signal(
                signal_type=SignalType.BUY,
                instrument=context.instrument,
                strength=0.8,
                reason="Test signal",
            )
        ]


class InvalidStrategy(BaseStrategy):
    """Strategy that fails validation."""

    name = ""  # Invalid - empty name
    instruments = []  # Invalid - no instruments
    periods = []  # Invalid - no periods

    def generate_signals(self, context: StrategyContext) -> list[Signal]:
        return []


@pytest.fixture(autouse=True)
def reset_running_strategies():
    """Reset the running strategies dict before each test."""
    strategy_service._running_strategies.clear()
    yield
    strategy_service._running_strategies.clear()


@pytest.fixture
def mock_strategy_registry():
    """Mock the StrategyRegistry."""
    with patch("tradingsystem.services.strategy_service.StrategyRegistry") as mock:
        yield mock


@pytest.fixture
def mock_series_service():
    """Mock the series_service."""
    with patch("tradingsystem.services.strategy_service.series_service") as mock:
        yield mock


@pytest.fixture
def mock_signal_service():
    """Mock the signal_service."""
    with patch("tradingsystem.services.strategy_service.signal_service") as mock:
        yield mock


@pytest.fixture
def sample_dataframe():
    """Create a sample OHLCV DataFrame."""
    return pd.DataFrame({
        "time": pd.date_range(start="2024-01-01", periods=100, freq="1min"),
        "open": [1.0850 + i * 0.0001 for i in range(100)],
        "high": [1.0855 + i * 0.0001 for i in range(100)],
        "low": [1.0845 + i * 0.0001 for i in range(100)],
        "close": [1.0852 + i * 0.0001 for i in range(100)],
        "volume": [1000] * 100,
    })


class TestInitializeStrategies:
    """Tests for strategy_service.initialize_strategies()."""

    def test_initialize_strategies(self):
        """initialize_strategies should discover and register built-in strategies."""
        with patch("tradingsystem.services.strategy_service.ensure_initialized") as mock_ensure, \
             patch("tradingsystem.services.strategy_service.discover_builtin_strategies") as mock_discover:

            mock_discover.return_value = 5

            count = strategy_service.initialize_strategies()

            mock_ensure.assert_called_once()
            mock_discover.assert_called_once()
            assert count == 5


class TestListStrategies:
    """Tests for strategy_service.list_strategies()."""

    def test_list_strategies(self, mock_strategy_registry):
        """list_strategies should return all registered strategies."""
        mock_strategy_registry.list_all.return_value = [
            {"id": "ma_crossover", "name": "MA Crossover"},
            {"id": "rsi_reversal", "name": "RSI Reversal"},
        ]

        result = strategy_service.list_strategies()

        assert len(result) == 2
        mock_strategy_registry.list_all.assert_called_once()


class TestGetStrategyInfo:
    """Tests for strategy_service.get_strategy_info()."""

    def test_get_strategy_info_found(self, mock_strategy_registry):
        """get_strategy_info should return strategy details."""
        mock_strategy_registry.get.return_value = MockStrategy

        result = strategy_service.get_strategy_info("mock_strategy")

        assert result is not None
        assert result["name"] == "mock_strategy"
        assert result["id"] == "mock_strategy"
        assert result["is_running"] is False

    def test_get_strategy_info_not_found(self, mock_strategy_registry):
        """get_strategy_info should return None for unknown strategy."""
        mock_strategy_registry.get.return_value = None

        result = strategy_service.get_strategy_info("unknown_strategy")

        assert result is None

    def test_get_strategy_info_running(self, mock_strategy_registry):
        """get_strategy_info should show running status."""
        mock_strategy_registry.get.return_value = MockStrategy

        # Mark as running
        strategy_service._running_strategies["mock_strategy"] = {
            "instance": MockStrategy(),
            "config": {"instruments": ["EUR_USD"]},
        }

        result = strategy_service.get_strategy_info("mock_strategy")

        assert result["is_running"] is True
        assert result["running_config"]["instruments"] == ["EUR_USD"]


class TestStartStrategy:
    """Tests for strategy_service.start_strategy()."""

    def test_start_strategy_success(self, mock_strategy_registry):
        """start_strategy should register and start a strategy."""
        mock_instance = MockStrategy()
        mock_strategy_registry.get_instance.return_value = mock_instance

        result = strategy_service.start_strategy(
            "mock_strategy",
            instruments=["EUR_USD"],
            periods=["M1"],
        )

        assert result["status"] == "started"
        assert result["strategy_id"] == "mock_strategy"
        assert result["instruments"] == ["EUR_USD"]
        assert "mock_strategy" in strategy_service._running_strategies

    def test_start_strategy_not_found(self, mock_strategy_registry):
        """start_strategy should raise for unknown strategy."""
        mock_strategy_registry.get_instance.return_value = None

        with pytest.raises(ValueError, match="Strategy not found"):
            strategy_service.start_strategy("unknown_strategy")

    def test_start_strategy_validation_failure(self, mock_strategy_registry):
        """start_strategy should raise if strategy validation fails."""
        mock_instance = InvalidStrategy()
        mock_strategy_registry.get_instance.return_value = mock_instance

        with pytest.raises(ValueError, match="validation failed"):
            strategy_service.start_strategy("invalid_strategy")

    def test_start_strategy_uses_default_instruments(self, mock_strategy_registry):
        """start_strategy should use strategy's default instruments if not provided."""
        mock_instance = MockStrategy()
        mock_strategy_registry.get_instance.return_value = mock_instance

        result = strategy_service.start_strategy("mock_strategy")

        assert result["instruments"] == ["EUR_USD", "GBP_USD"]
        assert result["periods"] == ["M1", "M5"]


class TestStopStrategy:
    """Tests for strategy_service.stop_strategy()."""

    def test_stop_strategy_success(self, mock_strategy_registry):
        """stop_strategy should stop a running strategy."""
        mock_instance = MockStrategy()
        mock_instance.on_start()

        strategy_service._running_strategies["mock_strategy"] = {
            "instance": mock_instance,
            "instruments": ["EUR_USD"],
            "periods": ["M1"],
            "started_at": datetime.now(timezone.utc),
            "last_run": None,
            "signals_generated": 5,
        }

        result = strategy_service.stop_strategy("mock_strategy")

        assert result["status"] == "stopped"
        assert result["signals_generated"] == 5
        assert "mock_strategy" not in strategy_service._running_strategies
        assert mock_instance.is_running is False

    def test_stop_strategy_not_running(self):
        """stop_strategy should raise for non-running strategy."""
        with pytest.raises(ValueError, match="Strategy not running"):
            strategy_service.stop_strategy("not_running_strategy")


class TestGetRunningStrategies:
    """Tests for strategy_service.get_running_strategies()."""

    def test_get_running_strategies_empty(self):
        """get_running_strategies should return empty list when none running."""
        result = strategy_service.get_running_strategies()

        assert result == []

    def test_get_running_strategies_with_strategies(self):
        """get_running_strategies should return all running strategies."""
        now = datetime.now(timezone.utc)
        strategy_service._running_strategies["strategy1"] = {
            "instance": MockStrategy(),
            "instruments": ["EUR_USD"],
            "periods": ["M1"],
            "started_at": now,
            "last_run": now,
            "signals_generated": 10,
        }
        strategy_service._running_strategies["strategy2"] = {
            "instance": MockStrategy(),
            "instruments": ["GBP_USD"],
            "periods": ["M5"],
            "started_at": now,
            "last_run": None,
            "signals_generated": 0,
        }

        result = strategy_service.get_running_strategies()

        assert len(result) == 2
        assert any(s["strategy_id"] == "strategy1" for s in result)
        assert any(s["strategy_id"] == "strategy2" for s in result)


class TestIsStrategyRunning:
    """Tests for strategy_service.is_strategy_running()."""

    def test_is_strategy_running_true(self):
        """is_strategy_running should return True for running strategy."""
        strategy_service._running_strategies["test_strategy"] = {}

        assert strategy_service.is_strategy_running("test_strategy") is True

    def test_is_strategy_running_false(self):
        """is_strategy_running should return False for non-running strategy."""
        assert strategy_service.is_strategy_running("not_running") is False


class TestRunStrategyOnce:
    """Tests for strategy_service.run_strategy_once()."""

    @pytest.mark.asyncio
    async def test_run_strategy_once_success(
        self, mock_strategy_registry, mock_series_service, mock_signal_service, sample_dataframe
    ):
        """run_strategy_once should execute strategy and return signals."""
        mock_instance = MockStrategy()
        mock_strategy_registry.get_instance.return_value = mock_instance

        mock_series_service.get_series_dataframe = AsyncMock(return_value=sample_dataframe)
        mock_signal_service.save_signals = AsyncMock()

        with patch("tradingsystem.services.strategy_service._calculate_strategy_indicators") as mock_calc:
            mock_calc.return_value = {"sma": pd.Series([1.0850] * 100)}

            signals = await strategy_service.run_strategy_once(
                strategy_id="mock_strategy",
                instrument="EUR_USD",
                period="M1",
            )

            assert len(signals) == 1
            assert signals[0].signal_type == SignalType.BUY
            mock_signal_service.save_signals.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_strategy_once_not_found(self, mock_strategy_registry):
        """run_strategy_once should raise for unknown strategy."""
        mock_strategy_registry.get_instance.return_value = None

        with pytest.raises(ValueError, match="Strategy not found"):
            await strategy_service.run_strategy_once(
                strategy_id="unknown",
                instrument="EUR_USD",
            )

    @pytest.mark.asyncio
    async def test_run_strategy_once_no_data(
        self, mock_strategy_registry, mock_series_service
    ):
        """run_strategy_once should return empty list when no candle data."""
        mock_instance = MockStrategy()
        mock_strategy_registry.get_instance.return_value = mock_instance

        mock_series_service.get_series_dataframe = AsyncMock(return_value=pd.DataFrame())

        signals = await strategy_service.run_strategy_once(
            strategy_id="mock_strategy",
            instrument="EUR_USD",
        )

        assert signals == []


class TestExecuteRunningStrategies:
    """Tests for strategy_service.execute_running_strategies()."""

    @pytest.mark.asyncio
    async def test_execute_running_strategies_success(
        self, mock_series_service, mock_signal_service, sample_dataframe
    ):
        """execute_running_strategies should run all registered strategies."""
        mock_instance = MockStrategy()
        mock_instance.on_start()

        strategy_service._running_strategies["mock_strategy"] = {
            "instance": mock_instance,
            "instruments": ["EUR_USD"],
            "periods": ["M1"],
            "started_at": datetime.now(timezone.utc),
            "last_run": None,
            "signals_generated": 0,
        }

        mock_series_service.get_series_dataframe = AsyncMock(return_value=sample_dataframe)
        mock_signal_service.save_signals = AsyncMock()

        with patch("tradingsystem.services.strategy_service._calculate_strategy_indicators") as mock_calc:
            mock_calc.return_value = {"sma": pd.Series([1.0850] * 100)}

            result = await strategy_service.execute_running_strategies()

            assert "mock_strategy" in result
            assert len(result["mock_strategy"]) >= 1

            # Check tracking was updated
            info = strategy_service._running_strategies["mock_strategy"]
            assert info["last_run"] is not None
            assert info["signals_generated"] >= 1

    @pytest.mark.asyncio
    async def test_execute_running_strategies_empty(self):
        """execute_running_strategies should return empty when none running."""
        result = await strategy_service.execute_running_strategies()

        assert result == {}

    @pytest.mark.asyncio
    async def test_execute_running_strategies_error_isolation(
        self, mock_series_service, mock_signal_service
    ):
        """execute_running_strategies should continue on individual errors."""
        mock_instance = MockStrategy()
        mock_instance.on_start()

        strategy_service._running_strategies["mock_strategy"] = {
            "instance": mock_instance,
            "instruments": ["EUR_USD"],
            "periods": ["M1"],
            "started_at": datetime.now(timezone.utc),
            "last_run": None,
            "signals_generated": 0,
        }

        # Make chart service raise an error
        mock_series_service.get_series_dataframe = AsyncMock(
            side_effect=Exception("Chart error")
        )

        # Should not raise, just log error
        result = await strategy_service.execute_running_strategies()

        # No signals due to error
        assert "mock_strategy" not in result or result["mock_strategy"] == []


class TestCalculateStrategyIndicators:
    """Tests for strategy_service._calculate_strategy_indicators()."""

    @pytest.mark.asyncio
    async def test_calculate_custom_indicator(self, sample_dataframe):
        """Should calculate custom indicators from registry."""
        strategy = MockStrategy()

        with patch("tradingsystem.services.strategy_service.IndicatorRegistry") as mock_registry:
            mock_indicator = MagicMock()
            mock_indicator.return_value.calculate.return_value = pd.Series([1.0] * 100)
            mock_registry.get.return_value = mock_indicator

            result = await strategy_service._calculate_strategy_indicators(
                strategy, sample_dataframe
            )

            assert "sma" in result

    @pytest.mark.asyncio
    async def test_calculate_pandas_ta_indicator(self, sample_dataframe):
        """Should fall back to pandas-ta for unknown indicators."""
        strategy = MockStrategy()

        with patch("tradingsystem.services.strategy_service.IndicatorRegistry") as mock_registry, \
             patch("tradingsystem.services.strategy_service.calculate_pandas_ta_indicator") as mock_pandas_ta:

            mock_registry.get.return_value = None  # Not a custom indicator
            mock_pandas_ta.return_value = pd.Series([1.0] * 100)

            result = await strategy_service._calculate_strategy_indicators(
                strategy, sample_dataframe
            )

            mock_pandas_ta.assert_called_once()
            assert "sma" in result

    @pytest.mark.asyncio
    async def test_calculate_indicator_error_handling(self, sample_dataframe):
        """Should handle indicator calculation errors gracefully."""
        strategy = MockStrategy()

        with patch("tradingsystem.services.strategy_service.IndicatorRegistry") as mock_registry:
            mock_registry.get.side_effect = Exception("Indicator error")

            # Should not raise
            result = await strategy_service._calculate_strategy_indicators(
                strategy, sample_dataframe
            )

            assert result == {}
