"""Chart data models."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ChartCreate(BaseModel):
    """Request model for creating a chart."""

    instrument: str
    period: str  # M1, M5, M15, H1, H4, D


class Chart(BaseModel):
    """Chart configuration."""

    id: UUID
    instrument: str
    period: str
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
