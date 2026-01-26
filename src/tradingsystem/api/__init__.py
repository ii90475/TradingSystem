"""API routes for TradingSystem."""

from tradingsystem.api.charts import router as charts_router
from tradingsystem.api.indicators import router as indicators_router
from tradingsystem.api.strategies import router as strategies_router
from tradingsystem.api.signals import router as signals_router
from tradingsystem.api.backtest import router as backtest_router
from tradingsystem.api.orders import router as orders_router
from tradingsystem.api.positions import router as positions_router
from tradingsystem.api.live_trading import router as live_trading_router

__all__ = [
    "charts_router",
    "indicators_router",
    "strategies_router",
    "signals_router",
    "backtest_router",
    "orders_router",
    "positions_router",
    "live_trading_router",
]
