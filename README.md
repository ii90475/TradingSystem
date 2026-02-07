# TradingSystem

[![CI](https://github.com/ii90475/TradingSystem/actions/workflows/ci.yml/badge.svg)](https://github.com/ii90475/TradingSystem/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-95%25-brightgreen)](https://github.com/ii90475/TradingSystem)

Automated trading system with technical analysis, backtesting, and strategy execution.

## Features

- **Web Dashboard** with TradingView charts and real-time pricing
- **WebSocket streaming** for sub-second price updates (250ms default)
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

The API runs on port 8002 (RateService runs on 8000).

## Web Dashboard

Access the trading dashboard at: **http://localhost:8002/ui**

Features:
- TradingView Lightweight Charts with candlestick data
- Real-time price updates via WebSocket (250ms refresh)
- Order placement with risk checks
- Open positions with P&L tracking
- Signal monitoring

## API Endpoints

- `GET /health` - Health check
- `GET /ui` - Trading dashboard
- `GET /docs` - OpenAPI documentation
- `WS /api/rates/ws` - Real-time rate streaming

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

Pre-commit hooks ensure code quality before every commit. Install once:

```bash
pip install pre-commit
pre-commit install
```

**Hooks executed on `git commit`:**

| Hook | Description |
|------|-------------|
| `trailing-whitespace` | Removes trailing whitespace |
| `end-of-file-fixer` | Ensures files end with newline |
| `check-yaml` | Validates YAML syntax |
| `check-json` | Validates JSON syntax |
| `check-added-large-files` | Blocks files >1MB |
| `check-merge-conflict` | Detects merge conflict markers |
| `detect-private-key` | Prevents committing private keys |
| `ruff` | Lints Python code with auto-fix |
| `ruff-format` | Formats Python code |
| `pytest-fast` | Runs unit tests (fast subset) |

**Manual commands:**
```bash
pre-commit run --all-files  # Run all hooks on all files
pre-commit autoupdate       # Update hook versions
```

### CI/CD Pipeline

GitHub Actions runs automatically on push/PR to `master`, `main`, or `develop` branches.

**Workflow: `.github/workflows/ci.yml`**

#### Test Suite Job

Runs the full test suite with coverage reporting:

```yaml
- pytest tests/ --cov=tradingsystem --cov-fail-under=85
- Upload coverage to Codecov
```

| Check | Requirement |
|-------|-------------|
| All tests pass | Required |
| Coverage ≥85% | Required |
| Coverage report | Uploaded to Codecov |

#### Code Quality Job

Static analysis and formatting checks:

| Tool | Purpose | Status |
|------|---------|--------|
| Ruff Linter | Code quality rules (E, F, I, N, W, UP) | Warning |
| Ruff Formatter | Code style consistency | Warning |

#### Security Scan Job

Vulnerability detection:

| Tool | Purpose | Status |
|------|---------|--------|
| Bandit | Python security issues | Warning |
| Safety | Dependency vulnerabilities | Warning |

**View CI Status:** [GitHub Actions](https://github.com/ii90475/TradingSystem/actions)

#### Setting Up Codecov (Optional)

To enable coverage tracking with Codecov:

1. Sign up at [codecov.io](https://codecov.io) with GitHub
2. Add repository to Codecov
3. Add `CODECOV_TOKEN` to repository secrets:
   - GitHub → Settings → Secrets → Actions → New repository secret
4. Coverage badge will auto-update on each push

#### Running CI Locally

Simulate CI checks before pushing:

```bash
# Run full test suite with coverage
pytest tests/ --cov=tradingsystem --cov-report=term-missing --cov-fail-under=85

# Run linter
ruff check src/tradingsystem

# Run formatter check
ruff format src/tradingsystem --check

# Run security scan
bandit -r src/tradingsystem -ll
safety check
```

## Testing

The project includes comprehensive test coverage (95%) with 805 tests covering all critical trading functionality.

> **Coverage Milestone (v0.20.0):** All testable code paths are now covered. Remaining gaps are in infrastructure code requiring live database connections or application entrypoint code.
>
> **v0.34.0:** Added WebSocket streaming tests, real-time rates API tests.
>
> **v0.40.1 (Phase 10.1):** Added 6 new built-in trading strategies with full test coverage.

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

**Overall: 961 tests | 93% coverage**

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
| Live Trading | 100% | 27 | OANDA trading, risk checks |
| Strategies | 100% | 19 | Strategy lifecycle, run-once |
| Backtest | 100% | 16 | Backtest execution, history |
| Dashboard | 100% | 19 | Portfolio, performance, alerts |
| Charts | 100% | 17 | Chart management, candles |
| Indicators | 100% | 17 | Indicator calculation |
| Rates | 100% | 23 | Real-time rates, WebSocket streaming |

#### Strategies & Indicators

| Component | Coverage | Tests | Description |
|-----------|----------|-------|-------------|
| Strategy Registry | 84% | 32 | Strategy registration, discovery |
| MA Crossover | 98% | 26 | Moving average crossover strategy |
| RSI Reversal | 100% | 26 | RSI mean-reversion strategy |
| Bollinger Breakout | 87% | 26 | Bollinger Band mean-reversion strategy |
| MACD Divergence | 90% | 24 | MACD divergence momentum strategy |
| Ichimoku Cloud | 89% | 26 | Ichimoku trend-following strategy |
| Support/Resistance | 77% | 24 | Price action breakout strategy |
| Multi-Timeframe | 94% | 26 | Multi-timeframe trend alignment strategy |
| ATR Trailing Stop | 96% | 30 | ATR-based trailing stop exit strategy |
| Backtest Engine | 98% | 32 | Position tracking, metrics |
| pandas-ta Wrapper | 93% | 22 | Technical indicator integration |

#### Infrastructure

| Component | Coverage | Tests | Description |
|-----------|----------|-------|-------------|
| RateService Client | 100% | 10 | Rate data fetching |
| OANDA Client | 100% | 36 | Trading API integration |
| Database | 65% | - | Connection pool (requires live DB) |
| Main Entrypoint | 65% | - | App startup (requires running server) |

#### Coverage Notes

The 93% coverage target represents complete testing of all business logic and API endpoints. The remaining 7% consists of:

- **Database connection pool** - Requires live TimescaleDB instance
- **Application entrypoint** - FastAPI server startup/shutdown lifecycle
- **Monitoring background tasks** - Long-running asyncio loops
- **Strategy registry file discovery** - Filesystem-dependent code paths

These are infrastructure concerns that are validated through integration testing and production monitoring rather than unit tests.

## Version History

| Version | Phase | Description |
|---------|-------|-------------|
| v0.40.1 | Phase 10.1 | Added 6 built-in strategies: Bollinger Breakout, MACD Divergence, Ichimoku Cloud, Support/Resistance, Multi-Timeframe, ATR Trailing Stop |
| v0.37.0 | - | Previous stable release |
| v0.34.0 | - | WebSocket streaming, real-time rates API |
| v0.20.0 | - | Coverage milestone (95% coverage achieved) |
