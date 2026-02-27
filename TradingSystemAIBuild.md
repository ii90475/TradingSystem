# Trading System AI Build

## Introduction

We have the RateService app running. We want to build a Trading App that uses the Rates data from RateService. The end goal is a system where we can build strategies and automate trading. We will build a process to introduce these automated strategies after backtesting and paper trading these strategies and build real time performance monitors to ensure stability and consistency in trading performance as well in future versions. For now, we are building the baseline.

## Definitions

- The Rates provided by RateService will be used by Charts. Charts are comprised of Instrument, a tradable entity, in this case a forex pair, a Period, i.e. M1 or 1D, and the Rates data for that Period.
- Indicators are formulaically derived data points that correspond to the Candle data of a chart.
- Candle data is comprised of Open, High, Low, Close Rates, and probably Volume, for each Period over a duration.
- Strategies are programmed executions based on Indicator conditions.
- Bars are Candles

## Assumptions & Presumptions

- We probably want to use Python in a manner similar to the RateService App for business logic
- We will need to plan for storing other data points i.e. Indicators & Strategies
- We would likely need to add a web-based front end, preferring vanilla javascript for performance, but open to guidance
- We plan on trading forex pairs first through leveraging Oanda API, and adding stocks via leveraging another brokerage's APIs at some point in the future

---

## System Architecture

### Service Overview

The system is composed of two independent services with a clear dependency chain:

```
┌─────────────────────────────────────────────────────────────────┐
│                        Infrastructure                           │
│                                                                 │
│  Docker Desktop ──► TimescaleDB Container (PostgreSQL)          │
│                          │                                      │
│                          ▼                                      │
│  ┌──────────────────────────────────────┐                       │
│  │        RateService (port 8000)       │                       │
│  │                                      │                       │
│  │  OANDA API ──► Rate Fetcher ──► DB   │                       │
│  │  Gap Detector ◄── Circuit Breakers   │                       │
│  │  Startup Backfill, Tick Validator    │                       │
│  │  REST API (22 endpoints)             │                       │
│  │  Prometheus Metrics (/metrics)       │                       │
│  └──────────────┬───────────────────────┘                       │
│                 │ HTTP (rates, candles, health)                  │
│                 ▼                                                │
│  ┌──────────────────────────────────────┐                       │
│  │      TradingSystem (port 8002)       │                       │
│  │                                      │                       │
│  │  Web Dashboard (TradingView Charts)  │                       │
│  │  WebSocket Streaming (250ms)         │                       │
│  │  Strategy Framework (8 strategies)   │                       │
│  │  Backtesting Engine                  │                       │
│  │  Paper Trading / Live Trading        │                       │
│  │  Order & Position Management         │                       │
│  │  Monitoring & SMS Alerts             │                       │
│  └──────────────────────────────────────┘                       │
└─────────────────────────────────────────────────────────────────┘
```

### Startup Dependency Chain

```
Docker Desktop (must enable "Start on login")
    └── TimescaleDB container (auto-started by RateService script)
            └── RateService (waits for DB health, port 8000)
                    └── TradingSystem (waits for RateService /health, port 8002)
```

### Data Flow

```
OANDA fxTrade API
    │
    ▼ (HTTP, every :00)
RateService Rate Fetcher
    │ (parallel fetch, 10 pairs)
    ▼
TimescaleDB (fx_candles hypertable)
    │ (continuous aggregates: 5m, 15m, 30m, 1h)
    │ (materialized views: 4h, 1d)
    ▼
RateService REST API
    │ (HTTP: /rates/current, /rates/{pair}/candles/{period})
    ▼
TradingSystem
    │ (proxies via RateServiceClient)
    ├──► Web Dashboard (TradingView Lightweight Charts)
    ├──► WebSocket Streaming (real-time price updates)
    ├──► Strategy Engine (signal generation)
    └──► Order/Position Management (paper or live via OANDA)
```

### Shared Database

Both services connect to the same TimescaleDB instance. RateService owns the `fx_candles` table and aggregate views. TradingSystem owns strategy, backtest, order, position, and signal tables.

---

## Current State

### TradingSystem — v0.43.0

| Area | Status |
|------|--------|
| Tests | 961 tests, 93% coverage |
| CI/CD | GitHub Actions (lint, test at 85% min, security scan) |
| Dashboard | TradingView charts, real-time WebSocket (250ms), order placement, P&L tracking |
| Strategies | 8 built-in (MA Crossover, RSI Reversal, Bollinger Breakout, MACD Divergence, Ichimoku Cloud, Support/Resistance, Multi-Timeframe, ATR Trailing Stop) |
| Backtesting | Full engine with performance metrics, equity curves |
| Trading | Paper trading (simulated), live trading via OANDA (with risk controls, emergency stop) |
| Indicators | 150+ via pandas-ta, custom indicator support |
| Monitoring | Component health checks, SMS alerts (Twilio), log rate monitoring |
| Deployment | launchd auto-start with dependency-aware scripts, watchdog |

### RateService — v0.42.0

| Area | Status |
|------|--------|
| Tests | 157 tests, 81% coverage |
| CI/CD | GitHub Actions (lint, test at 70% min, Docker build) |
| Data | 10 forex pairs from OANDA, M1 candles, 6 aggregate timeframes (5m–1d) |
| Self-healing | Startup backfill (48h), real-time gap detection, market-aware circuit breakers |
| API | 22 endpoints, admin auth, rate limiting, CORS, API versioning (/v1/) |
| Observability | Prometheus metrics (15+), structured JSON logging, correlation IDs, alert webhooks |
| Production readiness | 20/20 checklist criteria pass |

See [RateServiceAIBuild.md](../RateService/RateServiceAIBuild.md) for full detail.

---

## TradingSystem Development Phases

Current implementation plan is tracked in [`phase10.md`](phase10.md). Summary:

| Phase | Description | Status |
|-------|-------------|--------|
| 10.1 | UI Indicator Visualization — display indicators on TradingView charts | Done (v0.41.0) |
| 10.2 | Saved Strategy Configurations — StrategyInstance model, UI widget | Done (v0.42.2) |
| 10.3 | Trade Visualization — arrows/triangles/dots on chart for trades | Pending |
| 10.4 | Claude Indicator Creation — natural language to Python indicators | Pending |
| 10.5 | Performance Dashboard — metrics, thresholds, alerts | Pending |

---

## RateService

RateService is documented in its own repo. See:
- [RateServiceAIBuild.md](../RateService/RateServiceAIBuild.md) — project document (current state, accomplishments)
- [RateService architecture.md](../RateService/architecture.md) — detailed architecture reference
