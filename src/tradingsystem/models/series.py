"""Series data models."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class SeriesCreate(BaseModel):
    """Request model for creating a series."""

    instrument: str
    period: str  # M1, M5, M15, H1, H4, D


class Series(BaseModel):
    """Series configuration — an instrument at a specific period."""

    id: UUID
    instrument: str
    period: str
    created_at: datetime


class SeriesIndicatorCreate(BaseModel):
    """Request model for adding an indicator to a series."""

    indicator_type: str
    parameters: dict = {}


class SeriesIndicator(BaseModel):
    """Indicator configuration on a series."""

    id: UUID
    series_id: UUID
    indicator_type: str
    parameters: dict
    created_at: datetime
