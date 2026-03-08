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


