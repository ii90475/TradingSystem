#!/bin/bash
# Wait for RateService to be ready before starting TradingSystem

LOG_FILE="$HOME/Library/Logs/tradingsystem-startup.log"
MAX_WAIT=180  # seconds (longer since it depends on RateService starting first)

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}

log "Starting dependency check for TradingSystem..."

# Wait for RateService health endpoint
waited=0
while ! curl -sf --max-time 5 http://localhost:8000/health &>/dev/null; do
    if [ $waited -ge $MAX_WAIT ]; then
        log "ERROR: RateService not healthy after ${MAX_WAIT}s"
        exit 1
    fi
    log "Waiting for RateService... (${waited}s)"
    sleep 5
    waited=$((waited + 5))
done
log "RateService is healthy"

log "Starting TradingSystem..."
exec /Users/jamesconsole/.pyenv/versions/tradingsystem/bin/python -m uvicorn tradingsystem.main:app --host 0.0.0.0 --port 8002
