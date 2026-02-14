#!/bin/bash
# Robust Gap Repair Script
# - Disables background view refreshes during bulk operations
# - Chunks gaps into 7-day batches to prevent memory spikes
# - Tracks progress for resumability
# - Adds health checks before each batch
# - Refreshes views safely after completion

# Don't exit on error - we handle failures gracefully
set +e

RATESERVICE_URL="http://localhost:8000"
DB_CMD="docker exec rateservice-db psql -U postgres -d rateservice -t -A -c"
DB_CMD_FULL="docker exec rateservice-db psql -U postgres -d rateservice -c"

LOG_FILE="/Users/jamesconsole/Library/Logs/robust-backfill.log"
STATE_FILE="/Users/jamesconsole/Library/Logs/backfill-state.json"
CHUNK_DAYS=7  # Process gaps in 7-day chunks

PAIRS="EUR_USD GBP_USD USD_JPY USD_CHF AUD_USD USD_CAD NZD_USD EUR_GBP EUR_JPY GBP_JPY"

# Colors for terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    local msg="$(date '+%Y-%m-%d %H:%M:%S') - $1"
    echo -e "$msg" | tee -a "$LOG_FILE"
}

log_success() { log "${GREEN}SUCCESS${NC}: $1"; }
log_warn() { log "${YELLOW}WARNING${NC}: $1"; }
log_error() { log "${RED}ERROR${NC}: $1"; }
log_info() { log "${BLUE}INFO${NC}: $1"; }

# Initialize state file if it doesn't exist
init_state() {
    if [ ! -f "$STATE_FILE" ]; then
        echo '{"completed_chunks": [], "failed_chunks": [], "started_at": null, "paused_jobs": []}' > "$STATE_FILE"
    fi
}

# Update state file
update_state() {
    local key=$1
    local value=$2
    python3 -c "
import json
with open('$STATE_FILE', 'r') as f:
    state = json.load(f)
state['$key'] = $value
with open('$STATE_FILE', 'w') as f:
    json.dump(state, f, indent=2)
"
}

# Check if a chunk was already completed
is_chunk_completed() {
    local chunk_id=$1
    python3 -c "
import json
with open('$STATE_FILE', 'r') as f:
    state = json.load(f)
exit(0 if '$chunk_id' in state.get('completed_chunks', []) else 1)
"
}

# Mark chunk as completed
mark_chunk_completed() {
    local chunk_id=$1
    python3 -c "
import json
with open('$STATE_FILE', 'r') as f:
    state = json.load(f)
if '$chunk_id' not in state.get('completed_chunks', []):
    state.setdefault('completed_chunks', []).append('$chunk_id')
with open('$STATE_FILE', 'w') as f:
    json.dump(state, f, indent=2)
"
    log_success "Marked chunk completed: $chunk_id"
}

# Mark chunk as failed
mark_chunk_failed() {
    local chunk_id=$1
    local reason=$2
    python3 -c "
import json
with open('$STATE_FILE', 'r') as f:
    state = json.load(f)
failed = {'chunk': '$chunk_id', 'reason': '$reason', 'time': '$(date -Iseconds)'}
state.setdefault('failed_chunks', []).append(failed)
with open('$STATE_FILE', 'w') as f:
    json.dump(state, f, indent=2)
"
    log_error "Marked chunk failed: $chunk_id - $reason"
}

# Check database health before proceeding
check_db_health() {
    log_info "Checking database health..."

    # Check if database is accepting connections
    if ! $DB_CMD "SELECT 1;" >/dev/null 2>&1; then
        log_error "Database not responding"
        return 1
    fi

    # Check for recovery mode
    local in_recovery=$($DB_CMD "SELECT pg_is_in_recovery();" 2>/dev/null)
    if [ "$in_recovery" = "t" ]; then
        log_error "Database is in recovery mode"
        return 1
    fi

    # Check connection count (warn if high)
    local conn_count=$($DB_CMD "SELECT count(*) FROM pg_stat_activity WHERE state = 'active';" 2>/dev/null)
    if [ "$conn_count" -gt 50 ]; then
        log_warn "High connection count: $conn_count active connections"
    fi

    log_success "Database health OK"
    return 0
}

# Enable bulk mode in rateservice (pauses matview refresh)
enable_bulk_mode() {
    log_info "Enabling bulk mode in rateservice..."

    local result=$(curl -s -X POST "$RATESERVICE_URL/admin/bulk-mode?enable=true" 2>/dev/null)
    local bulk_mode=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin).get('bulk_mode', False))" 2>/dev/null)

    if [ "$bulk_mode" = "True" ]; then
        log_success "Bulk mode enabled in rateservice"
    else
        log_warn "Could not enable bulk mode in rateservice (may not be running or old version)"
    fi
}

# Disable bulk mode in rateservice (resumes matview refresh)
disable_bulk_mode() {
    log_info "Disabling bulk mode in rateservice..."

    local result=$(curl -s -X POST "$RATESERVICE_URL/admin/bulk-mode?enable=false" 2>/dev/null)
    local bulk_mode=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin).get('bulk_mode', False))" 2>/dev/null)

    if [ "$bulk_mode" = "False" ]; then
        log_success "Bulk mode disabled in rateservice"
    else
        log_warn "Could not disable bulk mode in rateservice"
    fi
}

# Disable TimescaleDB continuous aggregate policies
disable_cagg_policies() {
    log_info "Disabling TimescaleDB continuous aggregate refresh policies..."

    # Get all continuous aggregate policy job IDs
    local jobs=$($DB_CMD "
        SELECT job_id FROM timescaledb_information.jobs
        WHERE proc_name = 'policy_refresh_continuous_aggregate'
        AND scheduled = true;
    " 2>/dev/null)

    local paused_jobs="[]"
    for job_id in $jobs; do
        [ -z "$job_id" ] && continue
        log_info "  Disabling job $job_id"
        $DB_CMD "SELECT alter_job($job_id, scheduled => false);" >/dev/null 2>&1
        paused_jobs=$(python3 -c "import json; jobs=$paused_jobs; jobs.append($job_id); print(json.dumps(jobs))")
    done

    update_state "paused_jobs" "$paused_jobs"
    log_success "Disabled TimescaleDB continuous aggregate policies"
}

# Re-enable TimescaleDB continuous aggregate policies
enable_cagg_policies() {
    log_info "Re-enabling TimescaleDB continuous aggregate refresh policies..."

    local paused_jobs=$(python3 -c "
import json
with open('$STATE_FILE', 'r') as f:
    state = json.load(f)
print(' '.join(map(str, state.get('paused_jobs', []))))
")

    for job_id in $paused_jobs; do
        [ -z "$job_id" ] && continue
        log_info "  Enabling job $job_id"
        $DB_CMD "SELECT alter_job($job_id, scheduled => true);" >/dev/null 2>&1
    done

    update_state "paused_jobs" "[]"
    log_success "Re-enabled TimescaleDB continuous aggregate policies"
}

# Disable all background refresh operations
disable_background_refresh() {
    enable_bulk_mode
    disable_cagg_policies
}

# Re-enable all background refresh operations
enable_background_refresh() {
    enable_cagg_policies
    disable_bulk_mode
}

# Get candle count for verification
get_candle_count() {
    local pair=$1
    local from=$2
    local to=$3
    $DB_CMD "SELECT COUNT(*) FROM fx_candles WHERE pair='$pair' AND time >= '$from' AND time < '$to';" 2>/dev/null | tr -d ' '
}

# Submit a backfill request and wait for completion
backfill_chunk() {
    local pair=$1
    local from_date=$2
    local to_date=$3
    local chunk_id="${pair}_${from_date}_${to_date}"

    # Skip if already completed
    if is_chunk_completed "$chunk_id"; then
        log_info "Skipping already completed chunk: $chunk_id"
        return 0
    fi

    # Health check before each chunk
    if ! check_db_health; then
        log_error "Database unhealthy, waiting 60s before retry..."
        sleep 60
        if ! check_db_health; then
            mark_chunk_failed "$chunk_id" "database_unhealthy"
            return 1
        fi
    fi

    local before=$(get_candle_count "$pair" "$from_date" "$to_date")
    log_info "Backfilling $pair: $from_date to $to_date (existing: $before candles)"

    # Submit backfill request
    local result=$(curl -s -X POST "$RATESERVICE_URL/rates/${pair}/backfill" \
        -H "Content-Type: application/json" \
        -d "{\"from_time\": \"${from_date}T00:00:00Z\", \"to_time\": \"${to_date}T00:00:00Z\"}" \
        --max-time 30)

    local status=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','failed'))" 2>/dev/null)

    if [ "$status" != "started" ]; then
        log_error "Backfill request failed: $result"
        mark_chunk_failed "$chunk_id" "request_failed"
        return 1
    fi

    # Calculate wait time based on date range (roughly 1 second per day of data)
    local days_diff=$(( ($(date -j -f "%Y-%m-%d" "$to_date" +%s 2>/dev/null || date -d "$to_date" +%s) - $(date -j -f "%Y-%m-%d" "$from_date" +%s 2>/dev/null || date -d "$from_date" +%s)) / 86400 ))
    local wait_time=$(( days_diff * 3 + 30 ))  # 3 seconds per day + 30 base
    [ $wait_time -gt 180 ] && wait_time=180  # Cap at 3 minutes for 7-day chunks

    log_info "Waiting ${wait_time}s for backfill..."
    sleep $wait_time

    # Verify with retries
    local max_retries=3
    local retry=0
    while [ $retry -lt $max_retries ]; do
        local after=$(get_candle_count "$pair" "$from_date" "$to_date")
        local added=$((after - before))

        if [ "$added" -gt 0 ]; then
            log_success "Added $added candles (total: $after)"
            mark_chunk_completed "$chunk_id"
            return 0
        fi

        retry=$((retry + 1))
        if [ $retry -lt $max_retries ]; then
            log_warn "No candles added, retry $retry/$max_retries in 30s..."
            sleep 30
        fi
    done

    # Check if we actually have data (might have been a no-op due to existing data)
    local total=$(get_candle_count "$pair" "$from_date" "$to_date")
    if [ "$total" -gt 0 ]; then
        log_warn "No new candles but $total existing - marking as complete"
        mark_chunk_completed "$chunk_id"
        return 0
    fi

    log_error "Failed to add candles after $max_retries retries"
    mark_chunk_failed "$chunk_id" "no_candles_added"
    return 1
}

# Split a gap into chunks and process each
process_gap() {
    local pair=$1
    local gap_start=$2
    local gap_end=$3

    log_info "Processing gap: $pair from $gap_start to $gap_end"

    # Calculate chunk boundaries
    local current_start=$gap_start
    while [ "$(date -j -f "%Y-%m-%d" "$current_start" +%s 2>/dev/null || date -d "$current_start" +%s)" -lt "$(date -j -f "%Y-%m-%d" "$gap_end" +%s 2>/dev/null || date -d "$gap_end" +%s)" ]; do
        # Calculate chunk end (start + CHUNK_DAYS or gap_end, whichever is earlier)
        local chunk_end=$(date -j -v+${CHUNK_DAYS}d -f "%Y-%m-%d" "$current_start" "+%Y-%m-%d" 2>/dev/null || date -d "$current_start + $CHUNK_DAYS days" "+%Y-%m-%d")

        # Don't go past gap_end
        if [ "$(date -j -f "%Y-%m-%d" "$chunk_end" +%s 2>/dev/null || date -d "$chunk_end" +%s)" -gt "$(date -j -f "%Y-%m-%d" "$gap_end" +%s 2>/dev/null || date -d "$gap_end" +%s)" ]; then
            chunk_end=$gap_end
        fi

        backfill_chunk "$pair" "$current_start" "$chunk_end"

        # Move to next chunk
        current_start=$chunk_end
    done
}

# Find and fix all gaps for a pair
process_pair() {
    local pair=$1
    log ""
    log "=========================================="
    log "Processing $pair"
    log "=========================================="

    # Get gaps for this pair (> 4 days to skip weekends)
    local gaps=$($DB_CMD "
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
        log_success "No gaps found for $pair"
        return 0
    fi

    local gap_count=$(echo "$gaps" | wc -l | tr -d ' ')
    log_info "Found $gap_count gaps for $pair"

    for gap in $gaps; do
        local gap_start=$(echo "$gap" | cut -d'|' -f1)
        local gap_end=$(echo "$gap" | cut -d'|' -f2)

        [ -z "$gap_start" ] || [ -z "$gap_end" ] && continue

        process_gap "$pair" "$gap_start" "$gap_end"
    done
}

# Refresh materialized views safely (non-concurrent)
refresh_views() {
    log ""
    log "=========================================="
    log "Refreshing Materialized Views"
    log "=========================================="

    log_info "Refreshing fx_candles_1d (this may take a while)..."
    if $DB_CMD_FULL "REFRESH MATERIALIZED VIEW fx_candles_1d;" 2>&1; then
        log_success "fx_candles_1d refreshed"
    else
        log_error "Failed to refresh fx_candles_1d"
    fi

    log_info "Refreshing fx_candles_4h..."
    if $DB_CMD_FULL "REFRESH MATERIALIZED VIEW fx_candles_4h;" 2>&1; then
        log_success "fx_candles_4h refreshed"
    else
        log_error "Failed to refresh fx_candles_4h"
    fi
}

# Show final gap summary
show_summary() {
    log ""
    log "=========================================="
    log "Final Gap Summary"
    log "=========================================="

    $DB_CMD_FULL "
        WITH candle_gaps AS (
          SELECT pair, time::date as curr_date, LAG(time::date) OVER (PARTITION BY pair ORDER BY time) as prev_date
          FROM fx_candles WHERE time >= '2010-01-01'
        )
        SELECT pair, COUNT(*) as gap_count, SUM(curr_date - prev_date) as total_missing_days
        FROM candle_gaps
        WHERE curr_date - prev_date > 4
        GROUP BY pair
        ORDER BY total_missing_days DESC;
    " 2>/dev/null

    # Show state summary
    log ""
    log_info "State file: $STATE_FILE"
    python3 -c "
import json
with open('$STATE_FILE', 'r') as f:
    state = json.load(f)
print(f\"Completed chunks: {len(state.get('completed_chunks', []))}\"
print(f\"Failed chunks: {len(state.get('failed_chunks', []))}\"
for f in state.get('failed_chunks', [])[:5]:
    print(f\"  - {f['chunk']}: {f['reason']}\")
" 2>/dev/null || true
}

# Cleanup handler
cleanup() {
    log ""
    log_warn "Caught interrupt signal, cleaning up..."
    enable_background_refresh
    log_info "Cleanup complete. Run script again to resume from where it left off."
    exit 1
}

# Main
main() {
    trap cleanup SIGINT SIGTERM

    log "=========================================="
    log "Robust Gap Repair - Starting"
    log "Chunk size: $CHUNK_DAYS days"
    log "=========================================="

    init_state
    update_state "started_at" "\"$(date -Iseconds)\""

    # Initial health check
    if ! check_db_health; then
        log_error "Initial health check failed, aborting"
        exit 1
    fi

    # Disable all background refresh jobs
    disable_background_refresh

    # Process each pair
    for pair in $PAIRS; do
        process_pair "$pair"
    done

    # Re-enable all background refresh jobs
    enable_background_refresh

    # Refresh views
    refresh_views

    # Show summary
    show_summary

    log ""
    log "=========================================="
    log_success "Robust Gap Repair Complete"
    log "=========================================="
}

# Handle command line arguments
case "${1:-}" in
    --resume)
        log_info "Resuming from previous state..."
        main
        ;;
    --reset)
        log_warn "Resetting state file..."
        rm -f "$STATE_FILE"
        init_state
        log_success "State reset complete"
        ;;
    --status)
        if [ -f "$STATE_FILE" ]; then
            cat "$STATE_FILE" | python3 -m json.tool
        else
            echo "No state file found"
        fi
        ;;
    --help)
        echo "Usage: $0 [--resume|--reset|--status|--help]"
        echo ""
        echo "  (no args)  Start fresh or resume from saved state"
        echo "  --resume   Explicitly resume from saved state"
        echo "  --reset    Clear saved state and start fresh"
        echo "  --status   Show current state"
        echo "  --help     Show this help"
        ;;
    *)
        main
        ;;
esac
