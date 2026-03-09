"""Tests for chart strategy service."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

import pytest

from tradingsystem.models.chart_strategy import ChartStrategy
from tradingsystem.services import chart_strategy_service
from tradingsystem.strategies.base import BaseStrategy, IndicatorConfig


@pytest.fixture
def mock_cursor():
    """Create a mock database cursor."""
    cursor = AsyncMock()
    cursor.fetchone = AsyncMock()
    cursor.fetchall = AsyncMock()
    cursor.execute = AsyncMock()
    cursor.rowcount = 0
    cursor.connection = AsyncMock()
    cursor.connection.commit = AsyncMock()
    return cursor


@pytest.fixture
def sample_row():
    """Create sample chart strategy row."""
    return {
        "id": uuid4(),
        "chart_id": uuid4(),
        "strategy_id": "ma_crossover",
        "name": "MA Crossover Test",
        "parameters": {"fast_period": 10, "slow_period": 20},
        "enabled": False,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }


class TestCreateChartStrategy:
    """Tests for create_chart_strategy function."""

    @pytest.mark.asyncio
    async def test_creates_chart_strategy(self, mock_cursor, sample_row):
        """Should create a chart strategy."""
        mock_registry = MagicMock()
        mock_registry.get.return_value = {"id": "ma_crossover", "name": "MA Crossover"}

        with (
            patch("tradingsystem.services.chart_strategy_service.get_cursor") as mock_get,
            patch("tradingsystem.services.chart_strategy_service.StrategyRegistry", mock_registry),
        ):
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await chart_strategy_service.create_chart_strategy(
                chart_id=sample_row["chart_id"],
                strategy_id="ma_crossover",
                parameters={"fast_period": 10, "slow_period": 20},
                enabled=False,
            )

            assert isinstance(result, ChartStrategy)
            assert result.chart_id == sample_row["chart_id"]
            assert result.strategy_id == "ma_crossover"
            assert result.parameters == {"fast_period": 10, "slow_period": 20}
            assert result.enabled is False

    @pytest.mark.asyncio
    async def test_rejects_unknown_strategy(self, mock_cursor):
        """Should raise ValueError for unknown strategy."""
        mock_registry = MagicMock()
        mock_registry.get.return_value = None

        with patch("tradingsystem.services.chart_strategy_service.StrategyRegistry", mock_registry):
            with pytest.raises(ValueError, match="Unknown strategy"):
                await chart_strategy_service.create_chart_strategy(
                    chart_id=uuid4(),
                    strategy_id="nonexistent",
                )


class TestGetChartStrategy:
    """Tests for get_chart_strategy function."""

    @pytest.mark.asyncio
    async def test_returns_chart_strategy(self, mock_cursor, sample_row):
        """Should return chart strategy by ID."""
        mock_cursor.fetchone.return_value = sample_row

        with patch("tradingsystem.services.chart_strategy_service.get_cursor") as mock_get:
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await chart_strategy_service.get_chart_strategy(sample_row["id"])

            assert isinstance(result, ChartStrategy)
            assert result.id == sample_row["id"]

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, mock_cursor):
        """Should return None when not found."""
        mock_cursor.fetchone.return_value = None

        with patch("tradingsystem.services.chart_strategy_service.get_cursor") as mock_get:
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await chart_strategy_service.get_chart_strategy(uuid4())

            assert result is None


class TestListChartStrategies:
    """Tests for list_chart_strategies function."""

    @pytest.mark.asyncio
    async def test_returns_all(self, mock_cursor, sample_row):
        """Should return list of chart strategies."""
        mock_cursor.fetchall.return_value = [sample_row]

        with patch("tradingsystem.services.chart_strategy_service.get_cursor") as mock_get:
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await chart_strategy_service.list_chart_strategies()

            assert len(result) == 1
            assert isinstance(result[0], ChartStrategy)

    @pytest.mark.asyncio
    async def test_filters_by_chart_id(self, mock_cursor, sample_row):
        """Should filter by chart_id."""
        mock_cursor.fetchall.return_value = [sample_row]

        with patch("tradingsystem.services.chart_strategy_service.get_cursor") as mock_get:
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await chart_strategy_service.list_chart_strategies(
                chart_id=sample_row["chart_id"]
            )

            assert len(result) == 1
            # Verify the query included chart_id filter
            call_args = mock_cursor.execute.call_args
            assert "chart_id = %s" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_returns_empty_list(self, mock_cursor):
        """Should return empty list when none found."""
        mock_cursor.fetchall.return_value = []

        with patch("tradingsystem.services.chart_strategy_service.get_cursor") as mock_get:
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await chart_strategy_service.list_chart_strategies()

            assert result == []


class TestUpdateChartStrategy:
    """Tests for update_chart_strategy function."""

    @pytest.mark.asyncio
    async def test_updates_parameters(self, mock_cursor, sample_row):
        """Should update parameters."""
        updated = {**sample_row, "parameters": {"fast_period": 5}}
        mock_cursor.fetchone.return_value = updated

        with patch("tradingsystem.services.chart_strategy_service.get_cursor") as mock_get:
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await chart_strategy_service.update_chart_strategy(
                sample_row["id"],
                parameters={"fast_period": 5},
            )

            assert result.parameters == {"fast_period": 5}

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, mock_cursor):
        """Should return None when not found."""
        mock_cursor.fetchone.return_value = None

        with patch("tradingsystem.services.chart_strategy_service.get_cursor") as mock_get:
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await chart_strategy_service.update_chart_strategy(
                uuid4(),
                enabled=True,
            )

            assert result is None


class TestDeleteChartStrategy:
    """Tests for delete_chart_strategy function."""

    @pytest.mark.asyncio
    async def test_returns_true_when_deleted(self, mock_cursor):
        """Should return True when deleted."""
        mock_cursor.rowcount = 1

        with patch("tradingsystem.services.chart_strategy_service.get_cursor") as mock_get:
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await chart_strategy_service.delete_chart_strategy(uuid4())

            assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(self, mock_cursor):
        """Should return False when not found."""
        mock_cursor.rowcount = 0

        with patch("tradingsystem.services.chart_strategy_service.get_cursor") as mock_get:
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await chart_strategy_service.delete_chart_strategy(uuid4())

            assert result is False


class TestToggleEnabled:
    """Tests for toggle_enabled function."""

    @pytest.mark.asyncio
    async def test_toggles_enabled(self, mock_cursor, sample_row):
        """Should toggle enabled to True."""
        # First call returns the current state (enabled=False)
        # Second call returns the updated state (enabled=True)
        toggled = {**sample_row, "enabled": True}
        mock_cursor.fetchone.side_effect = [sample_row, toggled]

        with patch("tradingsystem.services.chart_strategy_service.get_cursor") as mock_get:
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await chart_strategy_service.toggle_enabled(sample_row["id"])

            assert result.enabled is True

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, mock_cursor):
        """Should return None when not found."""
        mock_cursor.fetchone.return_value = None

        with patch("tradingsystem.services.chart_strategy_service.get_cursor") as mock_get:
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await chart_strategy_service.toggle_enabled(uuid4())

            assert result is None


class TestAutoAddRequiredIndicators:
    """Tests for _auto_add_required_indicators."""

    @pytest.mark.asyncio
    async def test_adds_missing_indicators(self):
        """Should auto-add indicators the strategy requires but chart lacks."""
        chart_id = uuid4()

        class FakeStrategy(BaseStrategy):
            name = "Test"
            instruments = ["EUR_USD"]
            periods = ["H1"]
            required_indicators = [
                IndicatorConfig("sma", {"length": 20}),
                IndicatorConfig("rsi", {"length": 14}),
            ]
            def generate_signals(self, context):
                return []

        mock_registry = MagicMock()
        mock_registry.get.return_value = FakeStrategy

        with (
            patch("tradingsystem.services.chart_strategy_service.StrategyRegistry", mock_registry),
            patch("tradingsystem.services.chart_strategy_service.indicator_service") as mock_ind,
        ):
            mock_ind.get_chart_indicators = AsyncMock(return_value=[])
            mock_ind.add_indicator_to_chart = AsyncMock()

            added = await chart_strategy_service._auto_add_required_indicators(
                chart_id, "test_strategy"
            )

            assert set(added) == {"sma", "rsi"}
            assert mock_ind.add_indicator_to_chart.call_count == 2

    @pytest.mark.asyncio
    async def test_skips_existing_indicators(self):
        """Should not add indicators already on the chart."""
        chart_id = uuid4()

        class FakeStrategy(BaseStrategy):
            name = "Test"
            instruments = ["EUR_USD"]
            periods = ["H1"]
            required_indicators = [
                IndicatorConfig("sma", {"length": 20}),
            ]
            def generate_signals(self, context):
                return []

        existing_indicator = MagicMock()
        existing_indicator.indicator_type = "sma"

        mock_registry = MagicMock()
        mock_registry.get.return_value = FakeStrategy

        with (
            patch("tradingsystem.services.chart_strategy_service.StrategyRegistry", mock_registry),
            patch("tradingsystem.services.chart_strategy_service.indicator_service") as mock_ind,
        ):
            mock_ind.get_chart_indicators = AsyncMock(return_value=[existing_indicator])
            mock_ind.add_indicator_to_chart = AsyncMock()

            added = await chart_strategy_service._auto_add_required_indicators(
                chart_id, "test_strategy"
            )

            assert added == []
            mock_ind.add_indicator_to_chart.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_no_required_indicators(self):
        """Should return empty list when strategy has no required indicators."""
        class FakeStrategy(BaseStrategy):
            name = "Test"
            instruments = ["EUR_USD"]
            periods = ["H1"]
            required_indicators = []
            def generate_signals(self, context):
                return []

        mock_registry = MagicMock()
        mock_registry.get.return_value = FakeStrategy

        with patch("tradingsystem.services.chart_strategy_service.StrategyRegistry", mock_registry):
            added = await chart_strategy_service._auto_add_required_indicators(
                uuid4(), "test_strategy"
            )

            assert added == []


class TestGetStrategiesRequiringIndicator:
    """Tests for get_strategies_requiring_indicator."""

    @pytest.mark.asyncio
    async def test_finds_dependent_strategies(self, mock_cursor, sample_row):
        """Should return strategies that require a given indicator."""
        class FakeStrategy(BaseStrategy):
            name = "Test"
            instruments = ["EUR_USD"]
            periods = ["H1"]
            required_indicators = [
                IndicatorConfig("sma", {"length": 20}),
            ]
            def generate_signals(self, context):
                return []

        mock_cursor.fetchall.return_value = [sample_row]

        mock_registry = MagicMock()
        mock_registry.get.return_value = FakeStrategy

        with (
            patch("tradingsystem.services.chart_strategy_service.get_cursor") as mock_get,
            patch("tradingsystem.services.chart_strategy_service.StrategyRegistry", mock_registry),
        ):
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await chart_strategy_service.get_strategies_requiring_indicator(
                sample_row["chart_id"], "sma"
            )

            assert len(result) == 1
            assert result[0].strategy_id == "ma_crossover"

    @pytest.mark.asyncio
    async def test_returns_empty_for_unused_indicator(self, mock_cursor, sample_row):
        """Should return empty list when no strategy needs the indicator."""
        class FakeStrategy(BaseStrategy):
            name = "Test"
            instruments = ["EUR_USD"]
            periods = ["H1"]
            required_indicators = [
                IndicatorConfig("sma", {"length": 20}),
            ]
            def generate_signals(self, context):
                return []

        mock_cursor.fetchall.return_value = [sample_row]

        mock_registry = MagicMock()
        mock_registry.get.return_value = FakeStrategy

        with (
            patch("tradingsystem.services.chart_strategy_service.get_cursor") as mock_get,
            patch("tradingsystem.services.chart_strategy_service.StrategyRegistry", mock_registry),
        ):
            mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await chart_strategy_service.get_strategies_requiring_indicator(
                sample_row["chart_id"], "rsi"
            )

            assert result == []
