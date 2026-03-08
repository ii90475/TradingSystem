"""Tests for chart strategies API endpoints."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from tradingsystem.api.chart_strategies import (
    create_chart_strategy,
    delete_chart_strategy,
    get_chart_strategy,
    list_chart_strategies,
    toggle_chart_strategy,
    update_chart_strategy,
    CreateChartStrategyRequest,
    UpdateChartStrategyRequest,
)
from tradingsystem.models.chart import Chart
from tradingsystem.models.chart_strategy import ChartStrategy


@pytest.fixture
def sample_chart():
    """Create sample chart."""
    return Chart(
        id=uuid4(),
        name="Euro Scalper",
        series_id=uuid4(),
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_cs(sample_chart):
    """Create sample chart strategy."""
    return ChartStrategy(
        id=uuid4(),
        chart_id=sample_chart.id,
        strategy_id="ma_crossover",
        parameters={"fast_period": 10},
        enabled=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


class TestCreateChartStrategy:
    """Tests for create_chart_strategy endpoint."""

    @pytest.mark.asyncio
    async def test_creates_chart_strategy(self, sample_chart, sample_cs):
        """Should create a chart strategy."""
        with (
            patch("tradingsystem.api.chart_strategies.get_chart", new_callable=AsyncMock) as mock_get_chart,
            patch("tradingsystem.api.chart_strategies.chart_strategy_service") as mock_service,
        ):
            mock_get_chart.return_value = sample_chart
            mock_service.create_chart_strategy = AsyncMock(return_value=sample_cs)

            request = CreateChartStrategyRequest(
                chart_id=sample_chart.id,
                strategy_id="ma_crossover",
                parameters={"fast_period": 10},
                enabled=False,
            )
            result = await create_chart_strategy(request)

            assert result["strategy_id"] == "ma_crossover"
            assert result["chart_id"] == str(sample_chart.id)

    @pytest.mark.asyncio
    async def test_rejects_missing_chart(self):
        """Should return 404 when chart not found."""
        with patch("tradingsystem.api.chart_strategies.get_chart", new_callable=AsyncMock) as mock_get_chart:
            mock_get_chart.return_value = None

            request = CreateChartStrategyRequest(
                chart_id=uuid4(),
                strategy_id="ma_crossover",
            )
            with pytest.raises(HTTPException) as exc:
                await create_chart_strategy(request)

            assert exc.value.status_code == 404


class TestListChartStrategies:
    """Tests for list_chart_strategies endpoint."""

    @pytest.mark.asyncio
    async def test_returns_strategies(self, sample_cs):
        """Should return list of chart strategies."""
        with patch("tradingsystem.api.chart_strategies.chart_strategy_service") as mock_service:
            mock_service.list_chart_strategies = AsyncMock(return_value=[sample_cs])

            result = await list_chart_strategies()

            assert len(result) == 1
            assert result[0]["strategy_id"] == "ma_crossover"

    @pytest.mark.asyncio
    async def test_returns_empty_list(self):
        """Should return empty list when none found."""
        with patch("tradingsystem.api.chart_strategies.chart_strategy_service") as mock_service:
            mock_service.list_chart_strategies = AsyncMock(return_value=[])

            result = await list_chart_strategies()

            assert result == []


class TestGetChartStrategy:
    """Tests for get_chart_strategy endpoint."""

    @pytest.mark.asyncio
    async def test_returns_strategy(self, sample_cs):
        """Should return chart strategy by ID."""
        with patch("tradingsystem.api.chart_strategies.chart_strategy_service") as mock_service:
            mock_service.get_chart_strategy = AsyncMock(return_value=sample_cs)

            result = await get_chart_strategy(sample_cs.id)

            assert result["id"] == str(sample_cs.id)

    @pytest.mark.asyncio
    async def test_raises_404_when_not_found(self):
        """Should raise 404 when not found."""
        with patch("tradingsystem.api.chart_strategies.chart_strategy_service") as mock_service:
            mock_service.get_chart_strategy = AsyncMock(return_value=None)

            with pytest.raises(HTTPException) as exc:
                await get_chart_strategy(uuid4())

            assert exc.value.status_code == 404


class TestUpdateChartStrategy:
    """Tests for update_chart_strategy endpoint."""

    @pytest.mark.asyncio
    async def test_updates_strategy(self, sample_cs):
        """Should update chart strategy."""
        updated = ChartStrategy(
            id=sample_cs.id,
            chart_id=sample_cs.chart_id,
            strategy_id=sample_cs.strategy_id,
            parameters={"fast_period": 5},
            enabled=True,
            created_at=sample_cs.created_at,
            updated_at=datetime.now(timezone.utc),
        )
        with patch("tradingsystem.api.chart_strategies.chart_strategy_service") as mock_service:
            mock_service.update_chart_strategy = AsyncMock(return_value=updated)

            request = UpdateChartStrategyRequest(
                parameters={"fast_period": 5},
                enabled=True,
            )
            result = await update_chart_strategy(sample_cs.id, request)

            assert result["parameters"] == {"fast_period": 5}
            assert result["enabled"] is True

    @pytest.mark.asyncio
    async def test_raises_404_when_not_found(self):
        """Should raise 404 when not found."""
        with patch("tradingsystem.api.chart_strategies.chart_strategy_service") as mock_service:
            mock_service.update_chart_strategy = AsyncMock(return_value=None)

            request = UpdateChartStrategyRequest(enabled=True)
            with pytest.raises(HTTPException) as exc:
                await update_chart_strategy(uuid4(), request)

            assert exc.value.status_code == 404


class TestDeleteChartStrategy:
    """Tests for delete_chart_strategy endpoint."""

    @pytest.mark.asyncio
    async def test_deletes_strategy(self):
        """Should delete chart strategy."""
        with patch("tradingsystem.api.chart_strategies.chart_strategy_service") as mock_service:
            mock_service.delete_chart_strategy = AsyncMock(return_value=True)

            await delete_chart_strategy(uuid4())

    @pytest.mark.asyncio
    async def test_raises_404_when_not_found(self):
        """Should raise 404 when not found."""
        with patch("tradingsystem.api.chart_strategies.chart_strategy_service") as mock_service:
            mock_service.delete_chart_strategy = AsyncMock(return_value=False)

            with pytest.raises(HTTPException) as exc:
                await delete_chart_strategy(uuid4())

            assert exc.value.status_code == 404


class TestToggleChartStrategy:
    """Tests for toggle_chart_strategy endpoint."""

    @pytest.mark.asyncio
    async def test_toggles_enabled(self, sample_cs):
        """Should toggle enabled status."""
        toggled = ChartStrategy(
            id=sample_cs.id,
            chart_id=sample_cs.chart_id,
            strategy_id=sample_cs.strategy_id,
            parameters=sample_cs.parameters,
            enabled=True,
            created_at=sample_cs.created_at,
            updated_at=datetime.now(timezone.utc),
        )
        with patch("tradingsystem.api.chart_strategies.chart_strategy_service") as mock_service:
            mock_service.toggle_enabled = AsyncMock(return_value=toggled)

            result = await toggle_chart_strategy(sample_cs.id)

            assert result["enabled"] is True

    @pytest.mark.asyncio
    async def test_raises_404_when_not_found(self):
        """Should raise 404 when not found."""
        with patch("tradingsystem.api.chart_strategies.chart_strategy_service") as mock_service:
            mock_service.toggle_enabled = AsyncMock(return_value=None)

            with pytest.raises(HTTPException) as exc:
                await toggle_chart_strategy(uuid4())

            assert exc.value.status_code == 404
