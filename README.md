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
