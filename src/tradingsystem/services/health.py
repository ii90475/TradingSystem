"""Health state tracking for TradingSystem."""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    """Overall health status levels."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class HealthState:
    """Central health state tracker for the trading system."""

    database_healthy: bool = True
    database_error: str | None = None
    rateservice_healthy: bool = True
    rateservice_error: str | None = None
    rateservice_status: str = "unknown"
    scheduler_running: bool = False
    last_health_check: datetime | None = None
    active_strategies: int = 0
    open_positions: int = 0

    def record_database_health(self, healthy: bool, error: str | None = None) -> None:
        """Record database health status."""
        self.database_healthy = healthy
        self.database_error = error
        if not healthy:
            logger.error(
                "database_unhealthy",
                extra={"event": "health_update", "component": "database", "error": error},
            )

    def record_rateservice_health(
        self, healthy: bool, status: str = "unknown", error: str | None = None
    ) -> None:
        """Record RateService health status."""
        self.rateservice_healthy = healthy
        self.rateservice_status = status
        self.rateservice_error = error
        if not healthy:
            logger.error(
                "rateservice_unhealthy",
                extra={"event": "health_update", "component": "rateservice", "error": error},
            )

    def get_status(self) -> HealthStatus:
        """Determine overall health status."""
        # Unhealthy if critical components are down
        if not self.database_healthy:
            return HealthStatus.UNHEALTHY
        if not self.rateservice_healthy:
            return HealthStatus.UNHEALTHY

        # Degraded if RateService is degraded
        if self.rateservice_status == "degraded":
            return HealthStatus.DEGRADED

        return HealthStatus.HEALTHY

    def get_summary(self) -> dict:
        """Get complete health summary."""
        self.last_health_check = datetime.now(timezone.utc)

        return {
            "status": self.get_status().value,
            "timestamp": self.last_health_check.isoformat(),
            "database": {
                "healthy": self.database_healthy,
                "error": self.database_error,
            },
            "rateservice": {
                "healthy": self.rateservice_healthy,
                "status": self.rateservice_status,
                "error": self.rateservice_error,
            },
            "scheduler_running": self.scheduler_running,
            "active_strategies": self.active_strategies,
            "open_positions": self.open_positions,
        }


# Global health state instance
health_state = HealthState()
