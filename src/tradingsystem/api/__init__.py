"""API routes for TradingSystem."""

from tradingsystem.api.series import router as series_router
from tradingsystem.api.indicators import router as indicators_router
from tradingsystem.api.strategies import router as strategies_router
from tradingsystem.api.strategy_instances import router as strategy_instances_router
from tradingsystem.api.signals import router as signals_router
from tradingsystem.api.backtest import router as backtest_router
from tradingsystem.api.orders import router as orders_router
from tradingsystem.api.positions import router as positions_router
from tradingsystem.api.live_trading import router as live_trading_router
from tradingsystem.api.dashboard import router as dashboard_router
from tradingsystem.api.rates import router as rates_router
from tradingsystem.api.session import router as session_router

__all__ = [
    "series_router",
    "indicators_router",
    "strategies_router",
    "strategy_instances_router",
    "signals_router",
    "backtest_router",
    "orders_router",
    "positions_router",
    "live_trading_router",
    "dashboard_router",
    "rates_router",
    "session_router",
]
