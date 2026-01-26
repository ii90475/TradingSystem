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
from tradingsystem.services import strategy_service
from tradingsystem.api import (
    charts_router,
    indicators_router,
    strategies_router,
    signals_router,
    backtest_router,
    orders_router,
    positions_router,
    live_trading_router,
    dashboard_router,
)

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

    # Initialize strategies
    strategy_count = strategy_service.initialize_strategies()
    logger.info(f"Initialized {strategy_count} strategies")

    yield

    # Shutdown
    logger.info("Shutting down...")
    await close_pool()
    logger.info("Shutdown complete")


app = FastAPI(
    title=settings.app_name,
    description="Automated trading system with technical analysis, backtesting, and strategy execution",
    version="0.7.0",
    lifespan=lifespan,
)

# Register API routers
app.include_router(charts_router)
app.include_router(indicators_router)
app.include_router(strategies_router)
app.include_router(signals_router)
app.include_router(backtest_router)
app.include_router(orders_router)
app.include_router(positions_router)
app.include_router(live_trading_router)
app.include_router(dashboard_router)


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
        "version": "0.7.0",
        "description": "Automated trading system",
        "mode": "LIVE" if settings.live_trading_enabled else "PAPER",
        "endpoints": {
            "health": "/health",
            "dashboard": "/dashboard",
            "charts": "/charts",
            "indicators": "/indicators",
            "strategies": "/strategies",
            "signals": "/signals",
            "backtest": "/backtest",
            "orders": "/orders",
            "positions": "/positions",
            "live": "/live",
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
