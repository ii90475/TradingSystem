"""Order data models."""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel


class OrderSide(str, Enum):
    """Order side."""

    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    """Order type."""

    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


class OrderStatus(str, Enum):
    """Order status."""

    PENDING = "PENDING"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class OrderCreate(BaseModel):
    """Request model for creating an order."""

    instrument: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    price: Decimal | None = None  # Required for LIMIT/STOP orders
    strategy_id: str | None = None


class Order(BaseModel):
    """Order record."""

    id: UUID
    external_id: str | None = None  # Broker order ID
    strategy_id: str | None = None
    instrument: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    price: Decimal | None = None
    status: OrderStatus
    created_at: datetime
    filled_at: datetime | None = None
    filled_price: Decimal | None = None
    filled_quantity: Decimal | None = None
