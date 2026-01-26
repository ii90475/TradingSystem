"""Position data models."""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel


class PositionSide(str, Enum):
    """Position side."""

    LONG = "LONG"
    SHORT = "SHORT"


class PositionStatus(str, Enum):
    """Position status."""

    OPEN = "OPEN"
    CLOSED = "CLOSED"


class Position(BaseModel):
    """Trading position."""

    id: UUID
    instrument: str
    side: PositionSide
    quantity: Decimal
    entry_price: Decimal
    entry_time: datetime
    exit_price: Decimal | None = None
    exit_time: datetime | None = None
    status: PositionStatus
    strategy_id: str | None = None
    pnl: Decimal | None = None
    pnl_percent: Decimal | None = None


class PositionCreate(BaseModel):
    """Request model for opening a position."""

    instrument: str
    side: PositionSide
    quantity: Decimal
    entry_price: Decimal
    strategy_id: str | None = None


class PositionClose(BaseModel):
    """Request model for closing a position."""

    exit_price: Decimal


class PositionSummary(BaseModel):
    """Portfolio position summary."""

    total_positions: int
    open_positions: int
    closed_positions: int
    total_pnl: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
