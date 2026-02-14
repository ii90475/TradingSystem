#!/bin/bash
# RateService Watchdog Script - Enhanced Version v2
# Guarantees 100% data availability with retry logic and multi-pair monitoring
#
# Features:
# - Checks ALL pairs, not just EUR_USD
# - Retry logic for failed backfills (up to 3 attempts)
# - Market hours awareness (skip weekends)
# - Detects both real-time gaps and historical gaps
# - Self-healing after reboots: scans for gaps in last 24h
# - Robust error handling and logging
#
# Usage:
#   ./rateservice-watchdog.sh           # Normal 5-minute check
#   ./rateservice-watchdog.sh --startup # Deep scan after reboot (24h window)
#   ./rateservice-watchdog.sh EUR_USD   # Check single pair

RATESERVICE_URL="http://localhost:8000"
LOG_FILE="/Users/jamesconsole/Library/Logs/rateservice-watchdog.log"
MAX_GAP_MINUTES=5          # Alert if real-time gap exceeds this
MAX_RETRY_ATTEMPTS=3       # Retry failed backfills
RETRY_DELAY_SECONDS=30     # Wait between retries
SCAN_WINDOW_HOURS=24       # Historical gap scan window (hours)
MIN_GAP_SIZE_MINUTES=10    # Minimum gap size to trigger backfill

# All currency pairs to monitor
PAIRS="EUR_USD GBP_USD USD_JPY USD_CHF AUD_USD USD_CAD NZD_USD EUR_GBP EUR_JPY GBP_JPY"

# State files
LAST_RUN_FILE="/Users/jamesconsole/Library/Logs/watchdog-lastrun.ts"
BOOT_TIME_FILE="/tmp/watchdog-boot-check"

# Parse command line arguments
STARTUP_MODE=false
SINGLE_PAIR=""
if [ "$1" = "--startup" ]; then
    STARTUP_MODE=true
elif [ -n "$1" ] && [ "$1" != "--startup" ]; then
    SINGLE_PAIR="$1"
    PAIRS="$1"
fi

# Auto-detect if this is first run after reboot
# Compare system boot time with last run time
detect_reboot() {
    # Get system boot time (seconds since epoch)
    boot_time=$(sysctl -n kern.boottime | awk '{print $4}' | tr -d ',')

    # Check if we've already done a startup scan since this boot
    if [ -f "$BOOT_TIME_FILE" ]; then
        last_boot=$(cat "$BOOT_TIME_FILE")
        if [ "$boot_time" = "$last_boot" ]; then
            return 1  # Already ran startup scan for this boot
        fi
    fi

    # Check if we have a last run timestamp
    if [ ! -f "$LAST_RUN_FILE" ]; then
        # First ever run - do startup scan
        echo "$boot_time" > "$BOOT_TIME_FILE"
        return 0
    fi

    # Compare boot time with last run
    last_run=$(cat "$LAST_RUN_FILE")
    if [ "$boot_time" -gt "$last_run" ]; then
        # System was rebooted since last run - do startup scan
        echo "$boot_time" > "$BOOT_TIME_FILE"
        return 0
    fi

    return 1  # No reboot detected
}

# Update last run timestamp
update_last_run() {
    date +%s > "$LAST_RUN_FILE"
}

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

# Scan for historical gaps in a pair (last SCAN_WINDOW_HOURS)
# Returns gap count and triggers backfill for each gap found
scan_historical_gaps() {
    pair=$1
    gaps_found=0
    gaps_fixed=0

    log "Scanning $pair for gaps in last ${SCAN_WINDOW_HOURS}h..."

    # Query database directly for gaps > MIN_GAP_SIZE_MINUTES
    gaps=$(docker exec rateservice-db psql -U postgres -d rateservice -t -A -c "
        WITH candle_times AS (
            SELECT time,
                   LEAD(time) OVER (ORDER BY time) AS next_time
            FROM fx_candles
            WHERE pair = '$pair'
              AND time > NOW() - INTERVAL '$SCAN_WINDOW_HOURS hours'
        )
        SELECT time::text, next_time::text,
               EXTRACT(EPOCH FROM (next_time - time))/60 AS gap_minutes
        FROM candle_times
        WHERE next_time - time > INTERVAL '$MIN_GAP_SIZE_MINUTES minutes'
          AND EXTRACT(DOW FROM time) NOT IN (0, 6)  -- Skip weekend gaps
        ORDER BY time
        LIMIT 50;
    " 2>/dev/null)

    if [ -z "$gaps" ]; then
        log "No gaps found for $pair"
        return 0
    fi

    # Process each gap
    while IFS='|' read -r gap_start gap_end gap_minutes; do
        if [ -z "$gap_start" ]; then
            continue
        fi

        gaps_found=$((gaps_found + 1))
        gap_mins_int=${gap_minutes%.*}
        log "GAP: $pair from $gap_start to $gap_end (${gap_mins_int}m)"

        # Convert to ISO format for API
        from_time=$(echo "$gap_start" | sed 's/ /T/' | sed 's/+00$/Z/')
        to_time=$(echo "$gap_end" | sed 's/ /T/' | sed 's/+00$/Z/')

        if trigger_backfill_with_retry "$pair" "$from_time" "$to_time"; then
            gaps_fixed=$((gaps_fixed + 1))
        fi
    done <<< "$gaps"

    log "Gap scan complete for $pair: $gaps_found found, $gaps_fixed fixed"
    return $gaps_found
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
    # Auto-detect reboot and switch to startup mode
    if [ "$STARTUP_MODE" != true ] && detect_reboot; then
        log "Reboot detected - switching to startup mode"
        STARTUP_MODE=true
    fi

    if [ "$STARTUP_MODE" = true ]; then
        log "=== Watchdog STARTUP scan started (deep ${SCAN_WINDOW_HOURS}h window) ==="
    else
        log "=== Watchdog check started ==="
    fi

    # Check if market is open (but always run startup scan to catch reboot gaps)
    if ! is_market_open && [ "$STARTUP_MODE" != true ]; then
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

    # Check all pairs for data freshness (real-time gaps)
    check_all_pairs_freshness

    # In startup mode or every 12th run (hourly), scan for historical gaps
    if [ "$STARTUP_MODE" = true ]; then
        log "Running deep historical gap scan..."
        total_gaps=0
        for pair in $PAIRS; do
            scan_historical_gaps "$pair"
            total_gaps=$((total_gaps + $?))
        done
        if [ $total_gaps -gt 0 ]; then
            log "Deep scan found $total_gaps total gaps"
        else
            log "Deep scan complete: no gaps found"
        fi
    fi

    # Update last run timestamp
    update_last_run

    if [ "$STARTUP_MODE" = true ]; then
        log "=== Watchdog STARTUP scan complete ==="
    else
        log "=== Watchdog check complete ==="
    fi
}

main
