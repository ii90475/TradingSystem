"""Monitoring service for system health checks."""

import asyncio
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from tradingsystem.core.config import settings
from tradingsystem.core.database import check_database_health
from tradingsystem.core.oanda_trading import oanda_trading_client
from tradingsystem.core.rateservice import rateservice_client
from tradingsystem.services import strategy_service
from tradingsystem.services.alert_service import (
    AlertLevel,
    AlertType,
    alert_service,
)

logger = logging.getLogger(__name__)


class ComponentStatus(str, Enum):
    """Health status for a component."""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ComponentHealth:
    """Health state for a monitored component."""

    name: str
    status: ComponentStatus = ComponentStatus.UNKNOWN
    last_check: datetime | None = None
    last_healthy: datetime | None = None
    error: str | None = None
    details: dict = field(default_factory=dict)


class MonitoringService:
    """
    Comprehensive monitoring service for all system components.

    Runs health checks on a configurable interval via APScheduler.
    Alerts on component failures and recoveries (first occurrence only).
    """

    DOCKER_CONTAINER_NAME = "rateservice-db"

    def __init__(self) -> None:
        self._scheduler: AsyncIOScheduler | None = None
        self._running = False

        # Track component health
        self._components: dict[str, ComponentHealth] = {
            "docker": ComponentHealth(name="Docker Container"),
            "database": ComponentHealth(name="Database"),
            "rateservice": ComponentHealth(name="RateService"),
            "oanda": ComponentHealth(name="OANDA API"),
            "app": ComponentHealth(name="Application"),
        }

        # Track alerted failures to prevent spam
        self._alerted_failures: set[str] = set()

    @property
    def running(self) -> bool:
        """Check if monitoring is running."""
        return self._running

    async def start(self) -> None:
        """Start the monitoring service."""
        if not settings.monitoring_enabled:
            logger.info("Monitoring disabled by configuration")
            return

        if self._running:
            logger.warning("Monitoring service already running")
            return

        self._scheduler = AsyncIOScheduler()
        self._scheduler.add_job(
            self._run_health_checks,
            "interval",
            minutes=settings.monitoring_interval_minutes,
            id="health_checks",
            next_run_time=datetime.now(timezone.utc),  # Run immediately on start
        )
        self._scheduler.start()
        self._running = True

        logger.info(
            "monitoring_started",
            extra={"interval_minutes": settings.monitoring_interval_minutes},
        )

    async def stop(self) -> None:
        """Stop the monitoring service."""
        if self._scheduler and self._running:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None
            self._running = False
            logger.info("Monitoring service stopped")

    async def _run_health_checks(self) -> None:
        """Run all health checks concurrently."""
        try:
            await asyncio.gather(
                self._check_docker_container(),
                self._check_database(),
                self._check_rateservice(),
                self._check_oanda(),
                self._check_app_health(),
                return_exceptions=True,
            )

            logger.debug(
                "Health checks completed",
                extra={"statuses": {k: v.status.value for k, v in self._components.items()}},
            )
        except Exception as e:
            logger.error(f"Error running health checks: {e}")

    async def _check_docker_container(self) -> None:
        """Check if the Docker container is running."""
        component = self._components["docker"]
        component.last_check = datetime.now(timezone.utc)

        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    ["docker", "inspect", "-f", "{{.State.Running}}", self.DOCKER_CONTAINER_NAME],
                    capture_output=True,
                    text=True,
                    timeout=10,
                ),
            )

            if result.returncode == 0 and result.stdout.strip() == "true":
                self._record_healthy(component)
            else:
                error = result.stderr.strip() or "Container not running"
                self._record_failure(component, error)
        except FileNotFoundError:
            self._record_failure(component, "Docker not installed")
        except subprocess.TimeoutExpired:
            self._record_failure(component, "Docker command timed out")
        except Exception as e:
            self._record_failure(component, str(e))

    async def _check_database(self) -> None:
        """Check database connectivity."""
        component = self._components["database"]
        component.last_check = datetime.now(timezone.utc)

        try:
            health = await check_database_health()

            if health.get("healthy"):
                component.details = health.get("pool", {})
                self._record_healthy(component)
            else:
                self._record_failure(component, health.get("error", "Unknown error"))
        except Exception as e:
            self._record_failure(component, str(e))

    async def _check_rateservice(self) -> None:
        """Check RateService connectivity."""
        component = self._components["rateservice"]
        component.last_check = datetime.now(timezone.utc)

        try:
            health = await rateservice_client.check_health()

            if health.get("healthy"):
                component.details = {"status": health.get("status", "unknown")}
                self._record_healthy(component)
            else:
                self._record_failure(component, health.get("error", "Unknown error"))
        except Exception as e:
            self._record_failure(component, str(e))

    async def _check_oanda(self) -> None:
        """Check OANDA API connectivity."""
        component = self._components["oanda"]
        component.last_check = datetime.now(timezone.utc)

        # Skip if live trading is not enabled
        if not settings.live_trading_enabled:
            component.status = ComponentStatus.UNKNOWN
            component.details = {"reason": "Live trading disabled"}
            return

        try:
            connectivity = await oanda_trading_client.check_connectivity()

            if connectivity.get("connected"):
                component.details = {
                    "account_id": connectivity.get("account_id"),
                    "balance": str(connectivity.get("balance", "")),
                }
                self._record_healthy(component)
            else:
                self._record_failure(component, connectivity.get("error", "Unknown error"))
        except Exception as e:
            self._record_failure(component, str(e))

    async def _check_app_health(self) -> None:
        """Check application health (scheduler, strategies)."""
        component = self._components["app"]
        component.last_check = datetime.now(timezone.utc)

        try:
            running_strategies = strategy_service.get_running_strategies()
            scheduler_running = self._scheduler is not None and self._scheduler.running

            component.details = {
                "scheduler_running": scheduler_running,
                "active_strategies": len(running_strategies),
                "strategy_ids": [s["id"] for s in running_strategies],
            }

            # App is healthy if the scheduler is running
            if scheduler_running:
                self._record_healthy(component)
            else:
                self._record_failure(component, "Scheduler not running")
        except Exception as e:
            self._record_failure(component, str(e))

    def _record_healthy(self, component: ComponentHealth) -> None:
        """Record a component as healthy, alerting on recovery if needed."""
        was_unhealthy = component.status == ComponentStatus.UNHEALTHY
        component.status = ComponentStatus.HEALTHY
        component.last_healthy = datetime.now(timezone.utc)
        component.error = None

        # Alert on recovery
        if was_unhealthy and component.name in self._alerted_failures:
            self._alerted_failures.discard(component.name)
            alert_service.create_alert(
                AlertType.COMPONENT_RECOVERY,
                AlertLevel.INFO,
                f"{component.name} has recovered",
                {"component": component.name},
            )

    def _record_failure(self, component: ComponentHealth, error: str) -> None:
        """Record a component failure, alerting on first failure only."""
        component.status = ComponentStatus.UNHEALTHY
        component.error = error

        # Alert on first failure only
        if component.name not in self._alerted_failures:
            self._alerted_failures.add(component.name)
            alert_service.create_alert(
                AlertType.COMPONENT_FAILURE,
                AlertLevel.CRITICAL,
                f"{component.name} is unhealthy: {error}",
                {"component": component.name, "error": error},
            )

    def get_status(self) -> dict:
        """
        Get current monitoring status for all components.

        Returns:
            Dict with component statuses and monitoring info
        """
        components = {}
        for key, component in self._components.items():
            components[key] = {
                "name": component.name,
                "status": component.status.value,
                "last_check": component.last_check.isoformat() if component.last_check else None,
                "last_healthy": component.last_healthy.isoformat() if component.last_healthy else None,
                "error": component.error,
                "details": component.details,
            }

        # Count healthy/unhealthy
        healthy_count = sum(
            1 for c in self._components.values() if c.status == ComponentStatus.HEALTHY
        )
        total_count = len(self._components)

        return {
            "enabled": settings.monitoring_enabled,
            "running": self._running,
            "interval_minutes": settings.monitoring_interval_minutes,
            "summary": {
                "healthy": healthy_count,
                "unhealthy": total_count - healthy_count,
                "total": total_count,
            },
            "components": components,
        }

    async def run_check_now(self) -> dict:
        """
        Run health checks immediately (on-demand).

        Returns:
            Current status after checks
        """
        await self._run_health_checks()
        return self.get_status()


# Singleton instance
monitoring_service = MonitoringService()
