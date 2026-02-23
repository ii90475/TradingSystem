"""Strategy Instance model for saved strategy configurations.

A StrategyInstance binds a generic strategy (e.g., ma_crossover) to a specific
instrument, period, and parameter set, making it a trackable, reusable entity.

Example:
    - Strategy: "ma_crossover" (generic)
    - Instance: "GBP Trend Follower" = ma_crossover + GBP_USD + Daily + {fast: 20, slow: 50}
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4


@dataclass
class StrategyInstance:
    """A saved strategy configuration bound to a specific instrument and period."""

    id: UUID
    name: str  # User-friendly name, e.g., "GBP Trend Follower"
    strategy_id: str  # Reference to base strategy, e.g., "ma_crossover"
    instrument: str  # Currency pair, e.g., "GBP_USD"
    period: str  # Timeframe, e.g., "D", "H1", "M5"
    parameters: dict[str, Any]  # Strategy-specific params, e.g., {"fast_period": 20}
    enabled: bool  # Whether instance is active for signal generation
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        name: str,
        strategy_id: str,
        instrument: str,
        period: str,
        parameters: dict[str, Any] | None = None,
        enabled: bool = True,
    ) -> "StrategyInstance":
        """Factory method to create a new StrategyInstance."""
        now = datetime.now(timezone.utc)
        return cls(
            id=uuid4(),
            name=name,
            strategy_id=strategy_id,
            instrument=instrument,
            period=period,
            parameters=parameters or {},
            enabled=enabled,
            created_at=now,
            updated_at=now,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "id": str(self.id),
            "name": self.name,
            "strategy_id": self.strategy_id,
            "instrument": self.instrument,
            "period": self.period,
            "parameters": self.parameters,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "StrategyInstance":
        """Create instance from database row."""
        return cls(
            id=row["id"] if isinstance(row["id"], UUID) else UUID(row["id"]),
            name=row["name"],
            strategy_id=row["strategy_id"],
            instrument=row["instrument"],
            period=row["period"],
            parameters=row["parameters"] or {},
            enabled=row["enabled"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
