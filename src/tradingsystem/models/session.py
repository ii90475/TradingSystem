"""
Chart session models for persisting user chart state.

This module defines the data models for chart session persistence, allowing
users to save and restore their chart configuration (instrument, period,
and active indicators) across browser sessions.

Models:
    IndicatorConfig: Configuration for a single active indicator
    ChartSession: Complete chart session state
    ChartSessionUpdate: Request model for updating session state

The session state includes only configuration data, not calculated values.
Indicator values are always fetched fresh from the calculation API to ensure
real-time accuracy as candles update.
"""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class IndicatorConfig(BaseModel):
    """
    Configuration for an active indicator on the chart.

    This stores the indicator setup, not the calculated values. Values are
    fetched fresh from /api/indicators/calculate when the chart loads.

    Attributes:
        id: Unique identifier for this indicator instance (timestamp-based)
        name: Indicator name matching the calculation API (e.g., 'bbands', 'rsi')
        display_type: How to render - 'overlay' on price pane or 'pane' below
        params: Indicator-specific parameters (e.g., {'length': 14} for RSI)
        color: Primary line color as hex string (e.g., '#58a6ff')
        visible: Whether the indicator is currently shown on the chart
    """

    id: int = Field(..., description="Unique identifier for this indicator instance")
    name: str = Field(..., description="Indicator name (e.g., 'bbands', 'rsi')")
    display_type: str = Field("pane", description="Display type: 'overlay' or 'pane'")
    params: dict[str, Any] = Field(default_factory=dict, description="Indicator parameters")
    color: str = Field("#58a6ff", description="Line color for the indicator")
    visible: bool = Field(True, description="Whether the indicator is visible")


class ChartSession(BaseModel):
    """
    Persisted chart session state.

    Represents the complete state of a user's chart configuration that should
    be restored when they return to the dashboard. This is stored in the
    chart_sessions database table.

    Attributes:
        id: Database primary key (UUID)
        session_key: Session identifier, defaults to 'default' for single-user
        instrument: Currently selected currency pair (e.g., 'EUR_USD')
        period: Chart timeframe (e.g., 'M1', 'M5', 'H1', 'D')
        indicators: List of active indicators with their configurations
        updated_at: Timestamp of last update (for cache invalidation)
    """

    id: UUID = Field(default_factory=uuid4)
    session_key: str = Field("default", description="Session identifier (for multi-user support)")
    instrument: str = Field("EUR_USD", description="Current instrument")
    period: str = Field("M5", description="Current chart period")
    indicators: list[IndicatorConfig] = Field(default_factory=list, description="Active indicators")
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ChartSessionUpdate(BaseModel):
    """
    Request model for updating chart session.

    All fields are optional - only provided fields will be updated.
    This allows partial updates (e.g., just changing the period without
    resending the full indicator list).

    Attributes:
        instrument: New instrument to save (optional)
        period: New period to save (optional)
        indicators: New indicator list to save (optional)
    """

    instrument: str | None = None
    period: str | None = None
    indicators: list[IndicatorConfig] | None = None
