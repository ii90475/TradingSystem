#!/bin/bash
# RateService Watchdog Script
# Checks health and triggers backfill if data gaps are detected

RATESERVICE_URL="http://localhost:8000"
LOG_FILE="/Users/jamesconsole/Library/Logs/rateservice-watchdog.log"
MAX_GAP_MINUTES=5  # Alert if gap exceeds this

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}

# Check if RateService is responding
check_health() {
    response=$(curl -s -o /dev/null -w "%{http_code}" "$RATESERVICE_URL/health" --max-time 10)
    if [ "$response" != "200" ]; then
        log "ERROR: RateService not responding (HTTP $response)"
        return 1
    fi
    return 0
}

# Check for data gaps and trigger backfill if needed
check_data_freshness() {
    # Get latest candle time from RateService
    coverage=$(curl -s "$RATESERVICE_URL/rates/EUR_USD/coverage" --max-time 10)
    if [ -z "$coverage" ]; then
        log "ERROR: Could not get data coverage"
        return 1
    fi

    latest=$(echo "$coverage" | python3 -c "import sys, json; print(json.load(sys.stdin).get('latest', ''))" 2>/dev/null)
    if [ -z "$latest" ]; then
        log "ERROR: Could not parse latest timestamp"
        return 1
    fi

    # Calculate gap in minutes using Python for reliable timezone handling
    gap_minutes=$(python3 -c "
from datetime import datetime, timezone
latest = '$latest'
# Parse ISO format with timezone
if '+' in latest:
    latest = latest.replace('+00:00', '+0000')
    dt = datetime.strptime(latest, '%Y-%m-%dT%H:%M:%S%z')
else:
    dt = datetime.strptime(latest.replace('Z', ''), '%Y-%m-%dT%H:%M:%S').replace(tzinfo=timezone.utc)
now = datetime.now(timezone.utc)
gap = (now - dt).total_seconds() / 60
print(int(gap))
" 2>/dev/null)

    if [ -z "$gap_minutes" ]; then
        log "ERROR: Could not calculate gap"
        return 1
    fi

    if [ "$gap_minutes" -gt "$MAX_GAP_MINUTES" ]; then
        log "WARNING: Data gap detected: ${gap_minutes} minutes for EUR_USD"

        # Trigger backfill for all pairs
        trigger_backfill "$gap_minutes"
        return 1
    fi

    log "OK: Data is fresh (${gap_minutes}m gap)"
    return 0
}

# Trigger backfill for all configured pairs
trigger_backfill() {
    gap_minutes=$1

    # Use Python for reliable UTC time calculation
    times=$(python3 -c "
from datetime import datetime, timezone, timedelta
now = datetime.now(timezone.utc)
from_time = now - timedelta(minutes=$gap_minutes + 5)  # Add 5 min buffer
print(from_time.strftime('%Y-%m-%dT%H:%M:%SZ'))
print(now.strftime('%Y-%m-%dT%H:%M:%SZ'))
")
    from_time=$(echo "$times" | head -1)
    to_time=$(echo "$times" | tail -1)

    log "Triggering backfill from $from_time to $to_time"

    pairs="EUR_USD GBP_USD USD_JPY USD_CHF AUD_USD USD_CAD NZD_USD EUR_GBP EUR_JPY GBP_JPY"
    for pair in $pairs; do
        result=$(curl -s -X POST "$RATESERVICE_URL/rates/${pair}/backfill" \
            -H "Content-Type: application/json" \
            -d "{\"from_time\": \"$from_time\", \"to_time\": \"$to_time\"}" \
            --max-time 30)
        log "Backfill $pair: $result"
    done
}

# Restart RateService via launchctl
restart_service() {
    log "Attempting to restart RateService..."
    launchctl unload ~/Library/LaunchAgents/com.rateservice.app.plist 2>/dev/null
    sleep 2
    launchctl load ~/Library/LaunchAgents/com.rateservice.app.plist
    sleep 5

    if check_health; then
        log "RateService restarted successfully"
        return 0
    else
        log "ERROR: RateService failed to restart"
        return 1
    fi
}

# Main watchdog logic
main() {
    log "=== Watchdog check started ==="

    # Check if service is healthy
    if ! check_health; then
        log "RateService unhealthy, attempting restart..."
        restart_service
        # Wait for service to stabilize before checking data
        sleep 10
    fi

    # Check data freshness and backfill if needed
    check_data_freshness

    log "=== Watchdog check complete ==="
}

main
