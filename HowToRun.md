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

### Forex Market Hours

The forex market operates 24/5:
- **Opens:** Sunday 5:00 PM EST (22:00 UTC)
- **Closes:** Friday 5:00 PM EST (22:00 UTC)

No trading data is available on weekends.

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

### Friday Close Capture

RateService automatically captures the final market close price at exactly 5:00 PM New York time on Fridays. This ensures the last candle of the week has accurate close, high, and low values reflecting the final traded prices before the weekend.

The job runs 5 seconds after market close to ensure the final tick is captured, and updates:
- **Close**: Set to the final mid-price
- **High**: Updated if final price exceeds previous high
- **Low**: Updated if final price is below previous low

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

## 10. Troubleshooting

### RateService Not Collecting Data

1. Check if the service is running:
   ```bash
   launchctl list | grep rateservice
   ```

2. Check the logs:
   ```bash
   tail -50 ~/Library/Logs/rateservice.error.log
   ```

3. Verify market hours (no data on weekends)

4. Manually trigger backfill:
   ```bash
   /Users/jamesconsole/Code/TradingSystem/deploy/rateservice-watchdog.sh
   ```

### Chart Shows Stale Data

1. Check data freshness:
   ```bash
   curl http://localhost:8000/rates/EUR_USD/coverage
   ```

2. Trigger backfill for missing data:
   ```bash
   curl -X POST "http://localhost:8000/rates/EUR_USD/backfill" \
     -H "Content-Type: application/json" \
     -d '{"from_time": "2026-02-01T00:00:00Z", "to_time": "2026-02-06T00:00:00Z"}'
   ```

### Service Keeps Crashing

1. Check the watchdog log:
   ```bash
   tail -100 ~/Library/Logs/rateservice-watchdog.log
   ```

2. Restart all services:
   ```bash
   launchctl unload ~/Library/LaunchAgents/com.rateservice.app.plist
   launchctl unload ~/Library/LaunchAgents/com.tradingsystem.app.plist
   launchctl load ~/Library/LaunchAgents/com.rateservice.app.plist
   launchctl load ~/Library/LaunchAgents/com.tradingsystem.app.plist
   ```

### UI Slow or Unresponsive (Port Blocked)

If http://localhost:8002/ui is slow or timing out:

1. Check if something else is holding the port:
   ```bash
   lsof -i :8002
   ```

2. Kill zombie processes holding the port:
   ```bash
   # Find the PID from lsof output and kill it
   kill -9 <PID>
   ```

3. Verify the correct port in the launchd plist:
   ```bash
   grep 8002 ~/Library/LaunchAgents/com.tradingsystem.app.plist
   ```

4. Restart the service:
   ```bash
   launchctl unload ~/Library/LaunchAgents/com.tradingsystem.app.plist
   launchctl load ~/Library/LaunchAgents/com.tradingsystem.app.plist
   ```

5. Verify the server is responding:
   ```bash
   curl http://localhost:8002/health
   ```

### Historical Data Backfill

If historical data is missing or has gaps, use the robust backfill script:

```bash
# Run robust backfill for all pairs (auto-resumes from state)
./deploy/robust-backfill.sh

# Check current state
./deploy/robust-backfill.sh --status

# Reset state and start fresh
./deploy/robust-backfill.sh --reset

# Monitor progress
tail -f ~/Library/Logs/robust-backfill.log
```

#### Robust Backfill Features (v0.40.3)

The `robust-backfill.sh` script was designed to handle large-scale historical backfills without crashing the database:

| Feature | Description |
|---------|-------------|
| **7-day chunking** | Processes gaps in small batches to prevent memory spikes |
| **Bulk mode API** | Pauses RateService matview refresh during backfill |
| **TimescaleDB job control** | Disables continuous aggregate policies during bulk ops |
| **State tracking** | Saves progress to JSON file for crash recovery |
| **Health checks** | Verifies DB health before each batch |
| **Retry logic** | Retries failed chunks 3 times before marking failed |
| **Colored output** | Easy to see success/failure at a glance |

#### Why This Exists

The original backfill approach caused database crashes:
1. Large backfills inserted millions of rows
2. Background jobs (materialized view refresh, continuous aggregates) ran simultaneously
3. `REFRESH MATERIALIZED VIEW CONCURRENTLY` consumed too much memory
4. Linux OOM killer terminated postgres, causing database crash and recovery mode

The robust script prevents this by:
- Disabling background refresh jobs during bulk operations
- Processing data in smaller chunks
- Checking database health before each batch
- Using non-concurrent view refresh after completion

#### Bulk Mode API (RateService)

RateService exposes a bulk mode API to pause heavy background jobs:

```bash
# Enable bulk mode (pause matview refresh)
curl -X POST "http://localhost:8000/admin/bulk-mode?enable=true"

# Disable bulk mode (resume normal operation)
curl -X POST "http://localhost:8000/admin/bulk-mode?enable=false"

# Check status
curl http://localhost:8000/admin/bulk-mode
```

#### Manual Backfill

For smaller gaps, use the API directly:

```bash
# Check data coverage for a specific pair
curl http://localhost:8000/rates/EUR_USD/coverage

# Manual backfill for a specific date range
curl -X POST "http://localhost:8000/rates/GBP_USD/backfill" \
  -H "Content-Type: application/json" \
  -d '{"from_time": "2024-01-01T00:00:00Z", "to_time": "2024-12-31T00:00:00Z"}'
```

The enhanced watchdog (`deploy/rateservice-watchdog.sh`) runs every 5 minutes and:
- Monitors ALL 10 currency pairs (not just EUR_USD)
- Retries failed backfills up to 3 times
- Skips weekends when market is closed
- Automatically restarts RateService if unhealthy

## Recommended Workflow

1. **Backtest** strategies on historical data
2. **Paper trade** for real-time validation (no real money)
3. **Monitor** via dashboard and `/dashboard/monitoring` endpoint
4. **Live trade** only after consistent paper results
