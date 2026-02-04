# TradingSystem

[![CI](https://github.com/ii90475/TradingSystem/actions/workflows/ci.yml/badge.svg)](https://github.com/ii90475/TradingSystem/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-92%25-brightgreen)](https://github.com/ii90475/TradingSystem)

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

### Pre-commit Hooks

Install pre-commit hooks to ensure code quality before commits:

```bash
pip install pre-commit
pre-commit install
```

Hooks run automatically on `git commit`:
- Trailing whitespace removal
- YAML/JSON validation
- Ruff linting and formatting
- Fast unit tests

### CI/CD

GitHub Actions runs automatically on push/PR to master:
- **Test Suite**: Full pytest with coverage (must maintain 85%+)
- **Code Quality**: Ruff linting and formatting checks
- **Security Scan**: Bandit and safety dependency checks

View CI status: [Actions](https://github.com/ii90475/TradingSystem/actions)

## Testing

The project includes comprehensive test coverage (92%) with 684 tests covering all critical trading functionality.

```bash
# Run all tests
pytest tests/ -v

# Run with coverage report
pytest tests/ --cov=tradingsystem --cov-report=term-missing

# Run specific test categories
pytest tests/unit/           # Unit tests
pytest tests/infrastructure/ # Infrastructure tests
pytest tests/api/            # API endpoint tests
```

### Test Coverage Summary

**Overall: 684 tests | 92% coverage**

#### Core Services

| Service | Coverage | Tests | Description |
|---------|----------|-------|-------------|
| Risk Manager | 100% | 21 | Trade validation, position limits, circuit breaker |
| Order Service | 94% | 22 | Order creation, fills, cancellation |
| Position Service | 93% | 21 | P&L calculation, position lifecycle |
| Live Trading | 94% | 20 | OANDA integration, trade execution |
| Strategy Service | 99% | 19 | Strategy lifecycle, signal generation |
| Backtest Service | 98% | 16 | Backtest execution, result persistence |
| Performance Service | 97% | 15 | Metrics calculation, equity curves |
| Alert Service | 96% | 18 | Alert creation, handlers, history |
| Chart Service | 100% | 20 | Chart CRUD, candle data |
| Indicator Service | 99% | 22 | Indicator calculation, registry |
| Signal Service | 93% | 22 | Signal persistence, queries |
| Reconciliation | 97% | 17 | Position sync with OANDA |
| Paper Trading | 100% | 17 | Simulated trade execution |
| Health Service | 100% | 18 | System health tracking |
| Monitoring | 77% | 23 | Component health checks |
| Log Monitor | 99% | 32 | Error/warning rate detection |
| Twilio Handler | 96% | 19 | SMS alerts |

#### API Endpoints

| Router | Coverage | Tests | Description |
|--------|----------|-------|-------------|
| Orders | 96% | 17 | Order CRUD, trade execution |
| Positions | 97% | 18 | Position management, P&L |
| Live Trading | 87% | 20 | OANDA trading, risk checks |
| Strategies | 100% | 19 | Strategy lifecycle, run-once |
| Backtest | 100% | 16 | Backtest execution, history |
| Dashboard | 100% | 19 | Portfolio, performance, alerts |
| Charts | 100% | 17 | Chart management, candles |
| Indicators | 100% | 17 | Indicator calculation |

#### Strategies & Indicators

| Component | Coverage | Tests | Description |
|-----------|----------|-------|-------------|
| Strategy Registry | 84% | 32 | Strategy registration, discovery |
| MA Crossover | 98% | 26 | Moving average crossover strategy |
| RSI Reversal | 100% | 26 | RSI mean-reversion strategy |
| Backtest Engine | 98% | 32 | Position tracking, metrics |
| pandas-ta Wrapper | 93% | 22 | Technical indicator integration |

#### Infrastructure

| Component | Coverage | Tests | Description |
|-----------|----------|-------|-------------|
| RateService Client | 100% | 10 | Rate data fetching |
| OANDA Client | 68% | 17 | Trading API integration |
| Database | 65% | - | Connection pool (requires DB) |
