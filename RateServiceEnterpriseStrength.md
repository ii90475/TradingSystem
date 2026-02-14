# RateService Enterprise Strength Recommendations

## Current State Assessment

| Component | Status | Gap |
|-----------|--------|-----|
| Data source | OANDA only | Single point of failure |
| Fetch frequency | 1/minute | Sufficient for M1 candles |
| Gap detection | Every 5 min | Reactive, not proactive |
| Alerting | SMS via Twilio | No escalation, no on-call |
| Redundancy | None | Single server, single DB |

## Recommended Enhancements (Priority Order)

### 1. Multi-Source Redundancy (High Impact)
```
Primary:   OANDA API
Secondary: FXCM / Dukascopy / TrueFX
Tertiary:  ECB reference rates (daily fallback)
```
- Automatic failover when primary fails
- Cross-validate prices between sources (detect bad ticks)
- Configurable source priority per pair

**Status:** Planned for future implementation

### 2. Real-Time Gap Detection (High Impact)
```
Current:  Check freshness every 5 minutes (external watchdog)
Proposed: Detect gaps within 60 seconds of occurrence
```
- In-process monitoring (not external watchdog)
- Immediate backfill trigger on gap detection
- Per-pair health tracking with circuit breaker

**Status:** ✅ Implemented in v0.40.5

**Implementation details:**
- Gap detector runs at second 15 of each minute (after rate fetcher at 0)
- Scans last 30 minutes for gaps > 2 minutes
- Circuit breaker prevents API hammering (opens after 3 failures)
- API endpoints: `GET /rates/gaps/status`, `POST /rates/gaps/scan`

### 3. Tick Validation & Anomaly Detection
```python
# Reject ticks that are:
- > 5 standard deviations from rolling mean
- > 2% price move in 1 minute (flash crash detection)
- Stale (same price for > 5 minutes during market hours)
- Out of sequence (timestamp regression)
```

**Status:** Planned for future implementation

### 4. Database Resilience
```
Current:  Single PostgreSQL/TimescaleDB
Proposed:
- Streaming replication to standby
- Automated failover (Patroni or pg_auto_failover)
- Point-in-time recovery enabled
- Separate read replicas for queries
```

**Status:** Planned for future implementation

### 5. Observability Stack
```
Metrics:    Prometheus + Grafana dashboards
Logs:       Structured JSON → Loki or ELK
Traces:     OpenTelemetry for request tracking
Alerts:     PagerDuty with escalation policies
SLA:        99.9% uptime target with tracking
```

**Status:** Partial (Prometheus metrics exist, Grafana not deployed)

### 6. Queue-Based Architecture
```
Current:  Cron → Fetch → Insert (synchronous)
Proposed: Cron → Queue → Workers → Insert

Benefits:
- Backpressure handling
- Retry with exponential backoff
- Dead letter queue for failed inserts
- Horizontal scaling of workers
```

**Status:** Planned for future implementation

### 7. Circuit Breaker Pattern
```python
class RateSourceCircuitBreaker:
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Source failing, skip
    HALF_OPEN = "half"     # Testing recovery

    failure_threshold = 3   # Failures before open
    recovery_timeout = 60   # Seconds before half-open
```

**Status:** Planned for future implementation

## Implementation Phases

| Phase | Scope | Effort | Status |
|-------|-------|--------|--------|
| **Phase A** | Multi-source with failover | 1-2 weeks | Planned |
| **Phase B** | Real-time gap detection + circuit breaker | 1 week | ✅ Done |
| **Phase C** | Tick validation + anomaly detection | 1 week | Planned |
| **Phase D** | Database replication + failover | 2-3 days | Planned |
| **Phase E** | Observability stack (Prometheus/Grafana) | 2-3 days | Partial |
| **Phase F** | Queue-based architecture | 1-2 weeks | Planned |

## Quick Wins

1. **Add secondary data source** - FXCM or free ECN feed
2. **Move gap detection into RateService** - ✅ Done (v0.40.5)
3. **Add tick validation** - Reject obvious bad data
4. **Enable WAL archiving** - Point-in-time recovery for PostgreSQL

## Version History

| Version | Enhancement |
|---------|-------------|
| v0.40.5 | Real-time gap detection with immediate backfill |
| v0.40.4 | Self-healing watchdog with reboot detection |
| v0.40.3 | Robust backfill system with chunked processing |
