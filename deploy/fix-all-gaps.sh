#!/bin/bash
# Comprehensive Gap Repair Script
# Finds and fills ALL gaps for ALL pairs

RATESERVICE_URL="http://localhost:8000"
LOG_FILE="/Users/jamesconsole/Library/Logs/gap-repair.log"
DB_CMD="docker exec rateservice-db psql -U postgres -d rateservice -t -A -c"

PAIRS="EUR_USD GBP_USD USD_JPY USD_CHF AUD_USD USD_CAD NZD_USD EUR_GBP EUR_JPY GBP_JPY"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

get_candle_count() {
    pair=$1
    from=$2
    to=$3
    $DB_CMD "SELECT COUNT(*) FROM fx_candles WHERE pair='$pair' AND time >= '$from' AND time < '$to';" 2>/dev/null | tr -d ' '
}

backfill_with_verify() {
    pair=$1
    from=$2
    to=$3

    before=$(get_candle_count "$pair" "$from" "$to")
    log "  Backfilling $pair: $from to $to (before: $before candles)"

    # Submit backfill
    result=$(curl -s -X POST "$RATESERVICE_URL/rates/${pair}/backfill" \
        -H "Content-Type: application/json" \
        -d "{\"from_time\": \"${from}T00:00:00Z\", \"to_time\": \"${to}T00:00:00Z\"}" \
        --max-time 30)

    status=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','failed'))" 2>/dev/null)

    if [ "$status" != "started" ]; then
        log "  ERROR: Backfill request failed: $result"
        return 1
    fi

    # Wait and verify - longer waits for longer periods
    days_diff=$(( ($(date -j -f "%Y-%m-%d" "$to" +%s 2>/dev/null || date -d "$to" +%s) - $(date -j -f "%Y-%m-%d" "$from" +%s 2>/dev/null || date -d "$from" +%s)) / 86400 ))
    wait_time=$(( days_diff * 2 + 30 ))  # 2 seconds per day + 30 base
    [ $wait_time -gt 300 ] && wait_time=300  # Cap at 5 minutes

    log "  Waiting ${wait_time}s for backfill to complete..."
    sleep $wait_time

    after=$(get_candle_count "$pair" "$from" "$to")
    added=$((after - before))

    if [ "$added" -gt 0 ]; then
        log "  SUCCESS: Added $added candles (total: $after)"
        return 0
    else
        log "  WARNING: No candles added, retrying..."
        sleep 60
        after=$(get_candle_count "$pair" "$from" "$to")
        added=$((after - before))
        if [ "$added" -gt 0 ]; then
            log "  SUCCESS on retry: Added $added candles"
            return 0
        else
            log "  FAILED: Still no candles added"
            return 1
        fi
    fi
}

find_and_fix_gaps() {
    pair=$1
    log ""
    log "=== Processing $pair ==="

    # Get gaps for this pair (> 4 days to skip weekends)
    gaps=$($DB_CMD "
        WITH candle_gaps AS (
          SELECT
            time::date as curr_date,
            LAG(time::date) OVER (ORDER BY time) as prev_date
          FROM fx_candles
          WHERE pair = '$pair' AND time >= '2010-01-01'
        )
        SELECT prev_date || '|' || curr_date
        FROM candle_gaps
        WHERE curr_date - prev_date > 4
        ORDER BY prev_date;
    " 2>/dev/null)

    if [ -z "$gaps" ]; then
        log "No gaps found for $pair"
        return 0
    fi

    gap_count=$(echo "$gaps" | wc -l | tr -d ' ')
    log "Found $gap_count gaps for $pair"

    for gap in $gaps; do
        gap_start=$(echo "$gap" | cut -d'|' -f1)
        gap_end=$(echo "$gap" | cut -d'|' -f2)

        # Skip if dates are empty
        [ -z "$gap_start" ] || [ -z "$gap_end" ] && continue

        backfill_with_verify "$pair" "$gap_start" "$gap_end"
    done
}

main() {
    log "=========================================="
    log "Starting Comprehensive Gap Repair"
    log "=========================================="

    for pair in $PAIRS; do
        find_and_fix_gaps "$pair"
    done

    log ""
    log "=========================================="
    log "Gap Repair Complete - Refreshing Views"
    log "=========================================="

    $DB_CMD "REFRESH MATERIALIZED VIEW fx_candles_1d;" 2>/dev/null
    $DB_CMD "REFRESH MATERIALIZED VIEW fx_candles_4h;" 2>/dev/null

    log "Views refreshed"

    # Final verification
    log ""
    log "Final Gap Check:"
    remaining=$($DB_CMD "
        WITH candle_gaps AS (
          SELECT pair, time, LAG(time) OVER (PARTITION BY pair ORDER BY time) as prev_time
          FROM fx_candles WHERE time >= '2010-01-01'
        )
        SELECT COUNT(*) FROM candle_gaps WHERE time - prev_time > INTERVAL '4 days';
    " 2>/dev/null)
    log "Remaining gaps > 4 days: $remaining"
}

main
