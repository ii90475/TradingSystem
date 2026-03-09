"""FastAPI application entry point for TradingSystem."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from tradingsystem.core.config import settings
from tradingsystem.core.database import (
    check_database_health,
    close_pool,
    init_pool,
    init_schema,
)
from tradingsystem.core.rateservice import rateservice_client
from tradingsystem.core.websocket_manager import rate_manager
from tradingsystem.services.health import health_state
from tradingsystem.services import strategy_service
from tradingsystem.services.alert_service import alert_service
from tradingsystem.services.log_monitor import setup_log_monitoring
from tradingsystem.services.monitoring_service import monitoring_service
from tradingsystem.services.twilio_handler import twilio_handler
from tradingsystem.api import (
    series_router,
    charts_router,
    indicators_router,
    strategies_router,
    chart_strategies_router,
    signals_router,
    backtest_router,
    orders_router,
    positions_router,
    live_trading_router,
    dashboard_router,
    rates_router,
    session_router,
)
from tradingsystem.services import session_service

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

    # Set up log monitoring
    setup_log_monitoring()

    # Register Twilio SMS handler with alert service
    if twilio_handler.enabled:
        alert_service.register_handler(twilio_handler)
        logger.info("Twilio SMS handler registered")

    await init_pool()
    logger.info("Database pool initialized")

    try:
        await init_schema()
        logger.info("Database schema initialized")
    except Exception as e:
        logger.warning(f"Schema initialization skipped (may already exist): {e}")

    # Initialize session table
    try:
        await session_service.init_session_table()
    except Exception as e:
        logger.warning(f"Session table initialization skipped: {e}")

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

    # Start monitoring service
    await monitoring_service.start()

    # Start WebSocket rate broadcaster
    if settings.ws_enabled:
        await rate_manager.start_broadcasting()
        logger.info(f"WebSocket rate broadcaster started ({settings.ws_rate_poll_interval_ms}ms interval)")

    yield

    # Shutdown
    logger.info("Shutting down...")
    await rate_manager.stop_broadcasting()
    await monitoring_service.stop()
    await close_pool()
    logger.info("Shutdown complete")


app = FastAPI(
    title=settings.app_name,
    description="Automated trading system with technical analysis, backtesting, and strategy execution",
    version="0.48.1",
    lifespan=lifespan,
)

# Add CORS middleware for browser requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routers (original paths for backward compatibility)
app.include_router(series_router)
app.include_router(charts_router)
app.include_router(indicators_router)
app.include_router(strategies_router)
app.include_router(chart_strategies_router)
app.include_router(signals_router)
app.include_router(backtest_router)
app.include_router(orders_router)
app.include_router(positions_router)
app.include_router(live_trading_router)
app.include_router(dashboard_router)
app.include_router(rates_router)
app.include_router(session_router)

# Also register with /api prefix for frontend
app.include_router(series_router, prefix="/api")
app.include_router(charts_router, prefix="/api")
app.include_router(indicators_router, prefix="/api")
app.include_router(strategies_router, prefix="/api")
app.include_router(chart_strategies_router, prefix="/api")
app.include_router(signals_router, prefix="/api")
app.include_router(backtest_router, prefix="/api")
app.include_router(orders_router, prefix="/api")
app.include_router(positions_router, prefix="/api")
app.include_router(live_trading_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
app.include_router(rates_router, prefix="/api")
app.include_router(session_router, prefix="/api")

# Mount static files for frontend
FRONTEND_DIR = Path(__file__).parent.parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


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


@app.get("/ui")
async def serve_dashboard():
    """Serve the trading dashboard UI."""
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"error": "Frontend not found. Run from project root directory."}


@app.get("/")
async def root() -> dict:
    """Root endpoint with API info."""
    return {
        "name": settings.app_name,
        "version": "0.41.0",
        "description": "Automated trading system",
        "mode": "LIVE" if settings.live_trading_enabled else "PAPER",
        "ui": "/ui",
        "endpoints": {
            "health": "/health",
            "ui": "/ui",
            "api": {
                "dashboard": "/api/dashboard",
                "series": "/api/series",
                "charts": "/api/charts",
                "rates": "/api/rates",
                "indicators": "/api/indicators",
                "strategies": "/api/strategies",
                "signals": "/api/signals",
                "backtest": "/api/backtest",
                "orders": "/api/orders",
                "positions": "/api/positions",
                "live": "/api/live",
            },
            "docs": "/docs",
        },
    }


def main() -> None:
    """Run the application with uvicorn."""
    import uvicorn

    uvicorn.run(
        "tradingsystem.main:app",
        host="0.0.0.0",
        port=8002,  # Different port from RateService (8000)
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
