"""Indicator service for calculating and managing indicators."""

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

import pandas as pd

from tradingsystem.core.database import get_cursor
from tradingsystem.indicators import (
    IndicatorRegistry,
    calculate_pandas_ta_indicator,
    ensure_initialized,
)
from tradingsystem.models.chart import ChartIndicator, ChartIndicatorCreate
from tradingsystem.services import chart_service

logger = logging.getLogger(__name__)


async def add_indicator_to_chart(
    chart_id: UUID,
    indicator: ChartIndicatorCreate,
) -> ChartIndicator:
    """
    Add an indicator configuration to a chart.

    Args:
        chart_id: Chart UUID
        indicator: Indicator configuration

    Returns:
        Created ChartIndicator
    """
    # Verify indicator exists
    ensure_initialized()
    if not IndicatorRegistry.is_registered(indicator.indicator_type):
        raise ValueError(f"Unknown indicator: {indicator.indicator_type}")

    async with get_cursor() as cur:
        await cur.execute(
            """
            INSERT INTO chart_indicators (chart_id, indicator_type, parameters)
            VALUES (%s, %s, %s)
            RETURNING id, chart_id, indicator_type, parameters, created_at
            """,
            (chart_id, indicator.indicator_type, indicator.parameters),
        )
        row = await cur.fetchone()
        await cur.connection.commit()

        logger.info(
            "indicator_added",
            extra={
                "event": "indicator",
                "action": "add",
                "chart_id": str(chart_id),
                "indicator_type": indicator.indicator_type,
            },
        )

        return ChartIndicator(**row)


async def get_chart_indicators(chart_id: UUID) -> list[ChartIndicator]:
    """Get all indicators configured for a chart."""
    async with get_cursor() as cur:
        await cur.execute(
            """
            SELECT id, chart_id, indicator_type, parameters, created_at
            FROM chart_indicators
            WHERE chart_id = %s
            ORDER BY created_at
            """,
            (chart_id,),
        )
        rows = await cur.fetchall()
        return [ChartIndicator(**row) for row in rows]


async def delete_chart_indicator(indicator_id: UUID) -> bool:
    """Delete a chart indicator configuration."""
    async with get_cursor() as cur:
        await cur.execute(
            "DELETE FROM chart_indicators WHERE id = %s",
            (indicator_id,),
        )
        await cur.connection.commit()
        return cur.rowcount > 0


async def calculate_indicator(
    instrument: str,
    period: str,
    indicator_type: str,
    params: dict[str, Any] | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """
    Calculate an indicator for the given instrument.

    Args:
        instrument: Currency pair (e.g., "EUR_USD")
        period: Candle period (M1, M5, etc.)
        indicator_type: Indicator name
        params: Indicator parameters
        start: Start time for candles
        end: End time for candles
        limit: Number of candles to fetch

    Returns:
        Dict with indicator values and metadata
    """
    ensure_initialized()

    # Fetch candle data as DataFrame
    df = await chart_service.get_chart_dataframe(
        instrument=instrument,
        period=period,
        start=start,
        end=end,
        limit=limit,
    )

    if df.empty:
        return {
            "indicator": indicator_type,
            "params": params or {},
            "values": [],
        }

    params = params or {}

    # Check if it's a custom indicator
    custom_indicator_cls = IndicatorRegistry.get(indicator_type)
    if custom_indicator_cls:
        indicator = custom_indicator_cls()
        result = indicator.calculate(df, **params)
    else:
        # Try pandas-ta
        result = calculate_pandas_ta_indicator(df, indicator_type, **params)

    if result is None:
        raise ValueError(f"Failed to calculate indicator: {indicator_type}")

    # Convert result to serializable format
    if isinstance(result, pd.Series):
        values = [
            {"time": str(idx), "value": float(val) if pd.notna(val) else None}
            for idx, val in result.items()
        ]
    elif isinstance(result, pd.DataFrame):
        values = []
        for idx, row in result.iterrows():
            row_dict = {"time": str(idx)}
            for col in result.columns:
                val = row[col]
                row_dict[col] = float(val) if pd.notna(val) else None
            values.append(row_dict)
    else:
        values = []

    return {
        "indicator": indicator_type,
        "params": params,
        "values": values,
    }


def list_available_indicators() -> dict[str, list[dict[str, Any]]]:
    """
    List all available indicators.

    Returns:
        Dict with 'custom' and 'pandas_ta' indicator lists
    """
    ensure_initialized()

    custom_indicators = []
    for name in IndicatorRegistry.list_custom():
        info = IndicatorRegistry.get_info(name)
        if info:
            custom_indicators.append(info)

    pandas_ta_indicators = []
    for name in IndicatorRegistry.list_pandas_ta():
        info = IndicatorRegistry.get_info(name)
        if info:
            pandas_ta_indicators.append(info)

    return {
        "custom": custom_indicators,
        "pandas_ta": pandas_ta_indicators,
    }


def get_indicator_info(name: str) -> dict[str, Any] | None:
    """Get information about a specific indicator."""
    ensure_initialized()
    return IndicatorRegistry.get_info(name)
