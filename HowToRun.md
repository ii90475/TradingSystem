# TradingSystem Usage Guide

## 1. Start the Services

### Manual Start
```bash
# Terminal 1: Start RateService (forex data)
cd ~/Code/RateService
source ~/.pyenv/versions/rateservice/bin/activate
uvicorn rateservice.main:app --port 8000

# Terminal 2: Start TradingSystem
cd ~/Code/TradingSystem
source ~/.pyenv/versions/tradingsystem/bin/activate
uvicorn tradingsystem.main:app --port 8002
```

### Auto-Start on Boot (macOS)

Both services can be configured to start automatically on boot using launchd.

**Install the launch agents:**
```bash
# Copy plist files to LaunchAgents (if not already installed)
cp deploy/com.rateservice.app.plist ~/Library/LaunchAgents/
cp deploy/com.tradingsystem.app.plist ~/Library/LaunchAgents/
cp deploy/com.rateservice.watchdog.plist ~/Library/LaunchAgents/

# Load the services
launchctl load ~/Library/LaunchAgents/com.rateservice.app.plist
launchctl load ~/Library/LaunchAgents/com.tradingsystem.app.plist
launchctl load ~/Library/LaunchAgents/com.rateservice.watchdog.plist
```

**Manage services:**
```bash
# Check status
launchctl list | grep -E "(rateservice|tradingsystem)"

# Stop services
launchctl unload ~/Library/LaunchAgents/com.rateservice.app.plist
launchctl unload ~/Library/LaunchAgents/com.tradingsystem.app.plist
launchctl unload ~/Library/LaunchAgents/com.rateservice.watchdog.plist

# Start services
launchctl load ~/Library/LaunchAgents/com.rateservice.app.plist
launchctl load ~/Library/LaunchAgents/com.tradingsystem.app.plist
launchctl load ~/Library/LaunchAgents/com.rateservice.watchdog.plist

# View logs
tail -f ~/Library/Logs/rateservice.log
tail -f ~/Library/Logs/tradingsystem.log
tail -f ~/Library/Logs/rateservice-watchdog.log
```

### RateService Watchdog

The watchdog runs every 5 minutes and:
- Checks if RateService is responding
- Restarts the service if unhealthy
- Detects data gaps and triggers automatic backfill
- Logs all actions to `~/Library/Logs/rateservice-watchdog.log`

## 2. Paper Trading (Safe Testing)

**Execute a trade:**
```bash
# Buy 10,000 EUR/USD
curl -X POST http://localhost:8002/orders/trade \
  -H "Content-Type: application/json" \
  -d '{"instrument": "EUR_USD", "side": "BUY", "quantity": "10000"}'
```

**Check positions:**
```bash
curl http://localhost:8002/positions/open
```

**Close a position:**
```bash
curl -X POST http://localhost:8002/positions/{position_id}/close-at-market
```

**View account summary:**
```bash
curl http://localhost:8002/positions/account/summary
```

## 3. Run a Backtest

```bash
curl -X POST http://localhost:8002/backtest \
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

## 4. Web Dashboard

Open in browser: **http://localhost:8002/ui**

Features:
- TradingView candlestick charts
- Real-time price updates via WebSocket
- Order placement with risk checks
- Open positions with live P&L
- Signal monitoring

Or use API:
```bash
curl http://localhost:8002/dashboard/portfolio
curl http://localhost:8002/dashboard/performance
curl http://localhost:8002/dashboard/trades
```

## 5. Live Trading (When Ready)

**Enable live trading** (edit `.env`):
```bash
LIVE_TRADING_ENABLED=true
```

**Check risk status:**
```bash
curl http://localhost:8002/live/status
```

**Execute live trade:**
```bash
curl -X POST http://localhost:8002/live/trade \
  -H "Content-Type: application/json" \
  -d '{"instrument": "EUR_USD", "side": "BUY", "quantity": "100"}'
```

**Emergency stop:**
```bash
curl -X POST http://localhost:8002/live/emergency-close
```

## 6. System Monitoring

The system includes comprehensive internal monitoring with health checks and SMS alerts.

**Check monitoring status:**
```bash
curl http://localhost:8002/dashboard/monitoring
```

**Trigger immediate health check:**
```bash
curl -X POST http://localhost:8002/dashboard/monitoring/check
```

### Components Monitored

| Component | Description |
|-----------|-------------|
| Docker | `rateservice-db` container status |
| Database | PostgreSQL/TimescaleDB connectivity |
| RateService | Rate data service health |
| OANDA API | Live trading API (when enabled) |
| App | Scheduler status, active strategies |

### SMS Alerts (Optional)

Configure Twilio in `.env` to receive SMS alerts for critical failures:

```bash
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_FROM_NUMBER=+1234567890
TWILIO_TO_NUMBER=+1234567890
```

Alerts are sent on:
- **Component failure** - First occurrence only (no spam)
- **Component recovery** - When service comes back online
- **Log rate exceeded** - Too many errors/warnings in window

### Configuration

```bash
MONITORING_ENABLED=true           # Enable/disable monitoring
MONITORING_INTERVAL_MINUTES=1     # Check frequency
LOG_MONITOR_ERROR_THRESHOLD=10    # Errors before alert
LOG_MONITOR_WARNING_THRESHOLD=50  # Warnings before alert
LOG_MONITOR_WINDOW_SECONDS=300    # Sliding window (5 min)
```

## 6.5 Real-Time Rates

The system provides real-time price updates via WebSocket streaming.

### WebSocket Connection

Connect to `ws://localhost:8002/api/rates/ws` for real-time rate updates.

Message format:
```json
{
  "type": "rates",
  "timestamp": "2026-02-05T10:30:00Z",
  "data": [
    {
      "pair": "EUR_USD",
      "bid": "1.08500",
      "ask": "1.08520",
      "mid": "1.08510",
      "spread": "0.00020",
      "age_seconds": 0.5,
      "tradeable": true
    }
  ]
}
```

### HTTP Fallback

If WebSocket is unavailable, poll the REST API:
```bash
# Get current rate for a pair
curl http://localhost:8002/api/rates/current/EUR_USD

# Get all current rates
curl http://localhost:8002/api/rates/current

# Check WebSocket status
curl http://localhost:8002/api/rates/ws/status
```

### Configuration

```bash
WS_ENABLED=true              # Enable WebSocket endpoints (default: true)
WS_RATE_POLL_INTERVAL_MS=250 # Polling interval in ms (default: 250)
```

The 250ms default matches OANDA's maximum update frequency (4 prices/second per instrument).

## 7. Available Strategies

| Strategy | Description |
|----------|-------------|
| `ma_crossover` | SMA 10/20 crossover signals |
| `rsi_reversal` | RSI oversold/overbought reversal |

List strategies:
```bash
curl http://localhost:8002/strategies
```

## 8. Key API Docs

Interactive docs: **http://localhost:8002/docs**

## 9. OANDA Data Notes

### Daily Candle Boundary

OANDA uses **5 PM New York time (EST/EDT)** as the daily candle boundary, not UTC midnight.

| Timezone | Daily Candle Start |
|----------|-------------------|
| New York (EST) | 5:00 PM |
| UTC | 22:00 (winter) / 21:00 (summer) |

When aggregating M1 candles to daily, use the OANDA boundary:
```sql
-- Correct: OANDA trading day (5 PM EST = 22:00 UTC)
SELECT * FROM fx_candles
WHERE time >= '2026-01-29 22:00:00+00'
  AND time < '2026-01-30 22:00:00+00';

-- Incorrect: UTC midnight boundary
SELECT * FROM fx_candles
WHERE time >= '2026-01-30 00:00:00+00'
  AND time < '2026-01-31 00:00:00+00';
```

### Data Backfill

If data gaps occur, backfill via the RateService API:
```bash
curl -X POST "http://localhost:8000/rates/GBP_USD/backfill" \
  -H "Content-Type: application/json" \
  -d '{"from_time": "2026-01-29T22:00:00Z", "to_time": "2026-01-31T03:00:00Z"}'
```

Check data coverage:
```bash
curl http://localhost:8000/rates/GBP_USD/coverage
```

## Recommended Workflow

1. **Backtest** strategies on historical data
2. **Paper trade** for real-time validation (no real money)
3. **Monitor** via dashboard and `/dashboard/monitoring` endpoint
4. **Live trade** only after consistent paper results
