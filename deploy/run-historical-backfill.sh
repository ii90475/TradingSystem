#!/bin/bash
# Historical Backfill Script for TradingSystem
# Fills gaps in currency pair data from 2009-2026
#
# Run with: nohup ./run-historical-backfill.sh > ~/Library/Logs/historical-backfill.log 2>&1 &

RATESERVICE_URL="http://localhost:8000"
LOG_FILE="/Users/jamesconsole/Library/Logs/historical-backfill.log"

# Pairs that need historical backfill (data ends in 2009)
PAIRS="EUR_USD GBP_USD NZD_USD USD_CHF EUR_GBP EUR_JPY GBP_JPY"

# Break into yearly chunks to avoid overwhelming OANDA API
YEARS="2010 2011 2012 2013 2014 2015 2016 2017 2018 2019 2020 2021 2022 2023 2024 2025"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

backfill_year() {
    pair=$1
    year=$2
    from_time="${year}-01-01T00:00:00Z"
    to_time="$((year + 1))-01-01T00:00:00Z"

    log "Starting backfill: $pair $year ($from_time to $to_time)"

    result=$(curl -s -X POST "$RATESERVICE_URL/rates/${pair}/backfill" \
        -H "Content-Type: application/json" \
        -d "{\"from_time\": \"$from_time\", \"to_time\": \"$to_time\"}" \
        --max-time 120)

    status=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','failed'))" 2>/dev/null)

    if [ "$status" = "started" ]; then
        log "Backfill $pair $year: submitted successfully"
        # Wait for backfill to complete before continuing
        # Estimate: ~370K candles/year, ~5000 per request = ~75 requests
        # At ~1 request/second = ~75 seconds per year
        log "Waiting for $pair $year to complete (estimated 90 seconds)..."
        sleep 90
        return 0
    else
        log "ERROR: Backfill $pair $year failed: $result"
        return 1
    fi
}

check_coverage() {
    pair=$1
    coverage=$(curl -s "$RATESERVICE_URL/rates/${pair}/coverage" --max-time 10)
    total=$(echo "$coverage" | python3 -c "import sys,json; print(json.load(sys.stdin).get('total_candles', 0))" 2>/dev/null)
    echo "$total"
}

main() {
    log "=========================================="
    log "Starting Historical Backfill"
    log "Pairs: $PAIRS"
    log "Years: $YEARS"
    log "=========================================="

    for pair in $PAIRS; do
        log ""
        log "=== Processing $pair ==="

        before=$(check_coverage "$pair")
        log "$pair starting candle count: $before"

        for year in $YEARS; do
            backfill_year "$pair" "$year"
        done

        after=$(check_coverage "$pair")
        added=$((after - before))
        log "$pair complete. Candles added: $added (total: $after)"
    done

    log ""
    log "=========================================="
    log "Historical Backfill Complete"
    log "=========================================="

    # Final summary
    log ""
    log "Final Coverage Summary:"
    for pair in $PAIRS; do
        total=$(check_coverage "$pair")
        log "  $pair: $total candles"
    done
}

main
