"""ChartStrategy model — binds a strategy to a chart with parameters and toggle state."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4


@dataclass
class ChartStrategy:
    """A strategy assignment on a chart."""

    id: UUID
    chart_id: UUID
    strategy_id: str  # Reference to base strategy, e.g., "ma_crossover"
    name: str  # User-defined label, e.g., "Fast Euro Scalper"
    parameters: dict[str, Any]
    enabled: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        chart_id: UUID,
        strategy_id: str,
        name: str = "",
        parameters: dict[str, Any] | None = None,
        enabled: bool = False,
    ) -> "ChartStrategy":
        """Factory method to create a new ChartStrategy."""
        now = datetime.now(timezone.utc)
        return cls(
            id=uuid4(),
            chart_id=chart_id,
            strategy_id=strategy_id,
            name=name or strategy_id,
            parameters=parameters or {},
            enabled=enabled,
            created_at=now,
            updated_at=now,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "id": str(self.id),
            "chart_id": str(self.chart_id),
            "strategy_id": self.strategy_id,
            "name": self.name,
            "parameters": self.parameters,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "ChartStrategy":
        """Create instance from database row dict."""
        return cls(
            id=row["id"] if isinstance(row["id"], UUID) else UUID(row["id"]),
            chart_id=row["chart_id"] if isinstance(row["chart_id"], UUID) else UUID(row["chart_id"]),
            strategy_id=row["strategy_id"],
            name=row.get("name") or row["strategy_id"],
            parameters=row["parameters"] or {},
            enabled=row["enabled"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
