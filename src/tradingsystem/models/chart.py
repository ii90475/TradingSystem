"""Chart data models."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ChartCreate(BaseModel):
    """Request model for creating a chart."""

    name: str
    series_id: UUID


class Chart(BaseModel):
    """A named view on a Series with indicators attached."""

    id: UUID
    name: str
    series_id: UUID
    created_at: datetime


class ChartIndicatorCreate(BaseModel):
    """Request model for adding an indicator to a chart."""

    indicator_type: str
    parameters: dict = {}


class ChartIndicator(BaseModel):
    """Indicator configuration on a chart."""

    id: UUID
    chart_id: UUID
    indicator_type: str
    parameters: dict
    created_at: datetime
