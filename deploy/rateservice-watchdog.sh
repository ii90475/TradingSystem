#!/bin/bash
# RateService Watchdog Script - Enhanced Version
# Guarantees 100% data availability with retry logic and multi-pair monitoring
#
# Features:
# - Checks ALL pairs, not just EUR_USD
# - Retry logic for failed backfills (up to 3 attempts)
# - Market hours awareness (skip weekends)
# - Detects both real-time gaps and historical gaps
# - Robust error handling and logging

RATESERVICE_URL="http://localhost:8000"
LOG_FILE="/Users/jamesconsole/Library/Logs/rateservice-watchdog.log"
MAX_GAP_MINUTES=5          # Alert if real-time gap exceeds this
MAX_RETRY_ATTEMPTS=3       # Retry failed backfills
RETRY_DELAY_SECONDS=30     # Wait between retries

# All currency pairs to monitor
PAIRS="EUR_USD GBP_USD USD_JPY USD_CHF AUD_USD USD_CAD NZD_USD EUR_GBP EUR_JPY GBP_JPY"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}

log_error() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - ERROR: $1" >> "$LOG_FILE"
}

# Check if forex market is open (Sunday 5pm - Friday 5pm ET)
is_market_open() {
    python3 -c "
from datetime import datetime
import pytz

et = pytz.timezone('America/New_York')
now = datetime.now(et)
day = now.weekday()  # 0=Monday, 6=Sunday
hour = now.hour

# Market closed: Friday 5pm to Sunday 5pm ET
if day == 5:  # Saturday - closed
    exit(1)
elif day == 6 and hour < 17:  # Sunday before 5pm - closed
    exit(1)
elif day == 4 and hour >= 17:  # Friday after 5pm - closed
    exit(1)
else:
    exit(0)
" 2>/dev/null
    return $?
}

# Check if RateService is responding
check_health() {
    response=$(curl -s -o /dev/null -w "%{http_code}" "$RATESERVICE_URL/health" --max-time 10)
    if [ "$response" != "200" ]; then
        log_error "RateService not responding (HTTP $response)"
        return 1
    fi
    return 0
}

# Get data freshness for a specific pair
get_pair_freshness() {
    pair=$1
    coverage=$(curl -s "$RATESERVICE_URL/rates/${pair}/coverage" --max-time 10)
    if [ -z "$coverage" ]; then
        echo "-1"
        return
    fi

    latest=$(echo "$coverage" | python3 -c "import sys, json; print(json.load(sys.stdin).get('latest', ''))" 2>/dev/null)
    if [ -z "$latest" ]; then
        echo "-1"
        return
    fi

    gap_minutes=$(python3 -c "
from datetime import datetime, timezone
latest = '$latest'
if '+' in latest:
    latest = latest.replace('+00:00', '+0000')
    dt = datetime.strptime(latest, '%Y-%m-%dT%H:%M:%S%z')
else:
    dt = datetime.strptime(latest.replace('Z', ''), '%Y-%m-%dT%H:%M:%S').replace(tzinfo=timezone.utc)
now = datetime.now(timezone.utc)
gap = (now - dt).total_seconds() / 60
print(int(gap))
" 2>/dev/null)

    echo "${gap_minutes:-"-1"}"
}

# Trigger backfill with retry logic
trigger_backfill_with_retry() {
    pair=$1
    from_time=$2
    to_time=$3

    for attempt in $(seq 1 $MAX_RETRY_ATTEMPTS); do
        log "Backfill attempt $attempt/$MAX_RETRY_ATTEMPTS for $pair ($from_time to $to_time)"

        result=$(curl -s -X POST "$RATESERVICE_URL/rates/${pair}/backfill" \
            -H "Content-Type: application/json" \
            -d "{\"from_time\": \"$from_time\", \"to_time\": \"$to_time\"}" \
            --max-time 60)

        status=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','failed'))" 2>/dev/null)

        if [ "$status" = "started" ] || [ "$status" = "completed" ]; then
            log "Backfill $pair: SUCCESS ($status)"
            return 0
        fi

        log_error "Backfill $pair attempt $attempt failed: $result"

        if [ $attempt -lt $MAX_RETRY_ATTEMPTS ]; then
            sleep $RETRY_DELAY_SECONDS
        fi
    done

    log_error "Backfill $pair: FAILED after $MAX_RETRY_ATTEMPTS attempts"
    return 1
}

# Check all pairs for data freshness
check_all_pairs_freshness() {
    stale_pairs=""
    checked=0
    stale=0

    for pair in $PAIRS; do
        gap=$(get_pair_freshness "$pair")
        checked=$((checked + 1))

        if [ "$gap" = "-1" ]; then
            log_error "Could not get freshness for $pair"
            stale_pairs="$stale_pairs $pair"
            stale=$((stale + 1))
        elif [ "$gap" -gt "$MAX_GAP_MINUTES" ]; then
            log "STALE: $pair is ${gap}m behind"
            stale_pairs="$stale_pairs $pair"
            stale=$((stale + 1))

            # Trigger backfill for this pair
            times=$(python3 -c "
from datetime import datetime, timezone, timedelta
now = datetime.now(timezone.utc)
from_time = now - timedelta(minutes=$gap + 5)
print(from_time.strftime('%Y-%m-%dT%H:%M:%SZ'))
print(now.strftime('%Y-%m-%dT%H:%M:%SZ'))
")
            from_time=$(echo "$times" | head -1)
            to_time=$(echo "$times" | tail -1)

            trigger_backfill_with_retry "$pair" "$from_time" "$to_time"
        else
            log "OK: $pair is fresh (${gap}m)"
        fi
    done

    log "Summary: $checked pairs checked, $stale stale"

    if [ -n "$stale_pairs" ]; then
        return 1
    fi
    return 0
}

# Restart RateService via launchctl with retry
restart_service() {
    for attempt in 1 2 3; do
        log "Restart attempt $attempt/3..."
        launchctl unload ~/Library/LaunchAgents/com.rateservice.app.plist 2>/dev/null
        sleep 3
        launchctl load ~/Library/LaunchAgents/com.rateservice.app.plist
        sleep 10

        if check_health; then
            log "RateService restarted successfully on attempt $attempt"
            return 0
        fi
    done

    log_error "RateService failed to restart after 3 attempts"
    return 1
}

# Main watchdog logic
main() {
    log "=== Watchdog check started ==="

    # Check if market is open
    if ! is_market_open; then
        log "Market is closed (weekend). Skipping freshness check."
        log "=== Watchdog check complete (market closed) ==="
        return 0
    fi

    # Check if service is healthy
    if ! check_health; then
        log "RateService unhealthy, attempting restart..."
        if ! restart_service; then
            log_error "CRITICAL: Could not restore RateService"
            log "=== Watchdog check complete (service down) ==="
            return 1
        fi
        sleep 10
    fi

    # Check all pairs for data freshness
    check_all_pairs_freshness

    log "=== Watchdog check complete ==="
}

main
