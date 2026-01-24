"""FastAPI application entry point for TradingSystem."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from tradingsystem.core.config import settings
from tradingsystem.core.database import (
    check_database_health,
    close_pool,
    init_pool,
    init_schema,
)
from tradingsystem.core.rateservice import rateservice_client
from tradingsystem.services.health import health_state

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler for startup and shutdown."""
    # Startup
    logger.info(f"Starting {settings.app_name}...")

    await init_pool()
    logger.info("Database pool initialized")

    try:
        await init_schema()
        logger.info("Database schema initialized")
    except Exception as e:
        logger.warning(f"Schema initialization skipped (may already exist): {e}")

    # Check RateService connectivity
    rs_health = await rateservice_client.check_health()
    health_state.record_rateservice_health(
        rs_health["healthy"],
        rs_health.get("status", "unknown"),
        rs_health.get("error"),
    )
    if rs_health["healthy"]:
        logger.info(f"RateService connected: {settings.rateservice_url}")
    else:
        logger.warning(f"RateService not available: {rs_health.get('error')}")

    yield

    # Shutdown
    logger.info("Shutting down...")
    await close_pool()
    logger.info("Shutdown complete")


app = FastAPI(
    title=settings.app_name,
    description="Automated trading system with technical analysis, backtesting, and strategy execution",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check() -> dict:
    """
    Comprehensive health check endpoint.

    Returns health status for all components:
    - status: "healthy", "degraded", or "unhealthy"
    - database: connection pool health
    - rateservice: RateService connectivity
    - scheduler_running: whether background jobs are running
    """
    # Check database health
    db_health = await check_database_health()
    health_state.record_database_health(
        db_health["healthy"],
        db_health.get("error"),
    )

    # Check RateService health
    rs_health = await rateservice_client.check_health()
    health_state.record_rateservice_health(
        rs_health["healthy"],
        rs_health.get("status", "unknown"),
        rs_health.get("error"),
    )

    # Get full health summary
    summary = health_state.get_summary()

    # Add database pool details
    summary["database"]["pool"] = db_health.get("pool", {})

    return summary


@app.get("/health/simple")
async def health_check_simple() -> dict[str, str]:
    """Simple health check for load balancers (just returns status)."""
    # Quick check without full diagnostics
    db_health = await check_database_health()
    if not db_health["healthy"]:
        return {"status": "unhealthy"}

    rs_health = await rateservice_client.check_health()
    if not rs_health["healthy"]:
        return {"status": "degraded"}

    return {"status": "healthy"}


@app.get("/")
async def root() -> dict:
    """Root endpoint with API info."""
    return {
        "name": settings.app_name,
        "version": "0.1.0",
        "description": "Automated trading system",
        "endpoints": {
            "health": "/health",
            "docs": "/docs",
        },
    }


def main() -> None:
    """Run the application with uvicorn."""
    import uvicorn

    uvicorn.run(
        "tradingsystem.main:app",
        host="0.0.0.0",
        port=8001,  # Different port from RateService (8000)
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
