# TradingSystem Usage Guide

## 1. Start the Services

```bash
# Terminal 1: Start RateService (forex data)
cd ~/Code/RateService
source ~/.pyenv/versions/rateservice/bin/activate
uvicorn rateservice.main:app --port 8000

# Terminal 2: Start TradingSystem
cd ~/Code/TradingSystem
source ~/.pyenv/versions/tradingsystem/bin/activate
uvicorn tradingsystem.main:app --port 8001
```

## 2. Paper Trading (Safe Testing)

**Execute a trade:**
```bash
# Buy 10,000 EUR/USD
curl -X POST http://localhost:8001/orders/trade \
  -H "Content-Type: application/json" \
  -d '{"instrument": "EUR_USD", "side": "BUY", "quantity": "10000"}'
```

**Check positions:**
```bash
curl http://localhost:8001/positions/open
```

**Close a position:**
```bash
curl -X POST http://localhost:8001/positions/{position_id}/close-at-market
```

**View account summary:**
```bash
curl http://localhost:8001/positions/account/summary
```

## 3. Run a Backtest

```bash
curl -X POST http://localhost:8001/backtest \
  -H "Content-Type: application/json" \
  -d '{
    "strategy_id": "ma_crossover",
    "instrument": "EUR_USD",
    "start_date": "2026-01-20T00:00:00Z",
    "end_date": "2026-01-25T00:00:00Z",
    "initial_capital": "10000",
    "period": "M1"
  }'
```

## 4. Monitor via Dashboard

Open in browser: **http://localhost:8001/dashboard/**

Or use API:
```bash
curl http://localhost:8001/dashboard/portfolio
curl http://localhost:8001/dashboard/performance
curl http://localhost:8001/dashboard/trades
```

## 5. Live Trading (When Ready)

**Enable live trading** (edit `.env`):
```bash
LIVE_TRADING_ENABLED=true
```

**Check risk status:**
```bash
curl http://localhost:8001/live/status
```

**Execute live trade:**
```bash
curl -X POST http://localhost:8001/live/trade \
  -H "Content-Type: application/json" \
  -d '{"instrument": "EUR_USD", "side": "BUY", "quantity": "100"}'
```

**Emergency stop:**
```bash
curl -X POST http://localhost:8001/live/emergency-close
```

## 6. Available Strategies

| Strategy | Description |
|----------|-------------|
| `ma_crossover` | SMA 10/20 crossover signals |
| `rsi_reversal` | RSI oversold/overbought reversal |

List strategies:
```bash
curl http://localhost:8001/strategies
```

## 7. Key API Docs

Interactive docs: **http://localhost:8001/docs**

## Recommended Workflow

1. **Backtest** strategies on historical data
2. **Paper trade** for real-time validation (no real money)
3. **Monitor** via dashboard for performance
4. **Live trade** only after consistent paper results
