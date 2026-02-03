# TradingSystem

Automated trading system with technical analysis, backtesting, and strategy execution.

## Features

- Charts with 150+ technical indicators via pandas-ta
- Custom indicator support
- Strategy framework with Python code
- Backtesting engine with performance metrics
- Paper trading simulation
- Live trading via Oanda API (with risk controls)

## Installation

```bash
pip install -e .
```

## Configuration

Copy `.env.example` to `.env` and configure:
- `DATABASE_URL` - TimescaleDB connection string
- `RATESERVICE_URL` - RateService API URL
- `OANDA_API_KEY` - Oanda API key (for live trading)

## Running

```bash
tradingsystem
# or
python -m tradingsystem.main
```

The API runs on port 8001 (RateService runs on 8000).

## API Endpoints

- `GET /health` - Health check
- `GET /docs` - OpenAPI documentation

## Architecture

TradingSystem consumes rate data from RateService and provides:
1. Chart management with indicator configuration
2. Strategy execution framework
3. Signal generation and tracking
4. Order and position management
5. Backtesting capabilities

## Development

```bash
pip install -e ".[dev]"
pytest
```

## Testing

The project includes comprehensive test coverage for critical trading services:

```bash
# Run all tests
pytest tests/ -v

# Run with coverage report
pytest tests/ --cov=tradingsystem.services --cov-report=term-missing

# Run specific test categories
pytest tests/unit/           # Unit tests only
pytest tests/integration/    # Integration tests only
```

### Test Coverage

| Service | Coverage | Description |
|---------|----------|-------------|
| Risk Manager | 100% | Trade validation, position limits, circuit breaker |
| Order Service | 94% | Order creation, fills, cancellation |
| Position Service | 93% | P&L calculation, position lifecycle |
| Live Trading | 94% | OANDA integration, trade execution |
| Strategy Service | 99% | Strategy lifecycle, signal generation |
| Backtest Service | 98% | Backtest execution, result persistence |
| Performance Service | 97% | Metrics calculation, equity curves |

**Total: 122 tests with 96% coverage on core services**
