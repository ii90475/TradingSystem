"""Dashboard API endpoints for monitoring and visualization."""

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

from tradingsystem.services import performance_service
from tradingsystem.services.alert_service import alert_service, AlertLevel, AlertType

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/portfolio")
async def get_portfolio_snapshot() -> dict:
    """Get current portfolio state."""
    snapshot = await performance_service.get_portfolio_snapshot()
    return {
        "timestamp": snapshot.timestamp.isoformat(),
        "account_balance": str(snapshot.account_balance),
        "nav": str(snapshot.nav),
        "unrealized_pnl": str(snapshot.unrealized_pnl),
        "realized_pnl": str(snapshot.realized_pnl),
        "open_positions": snapshot.open_positions,
        "margin_used": str(snapshot.margin_used),
        "margin_available": str(snapshot.margin_available),
        "daily_pnl": str(snapshot.daily_pnl),
        "weekly_pnl": str(snapshot.weekly_pnl),
    }


@router.get("/performance")
async def get_performance_metrics(
    period: str = Query("all_time", description="daily, weekly, monthly, all_time"),
    strategy_id: str | None = Query(None, description="Filter by strategy"),
) -> dict:
    """Get performance metrics for a time period."""
    metrics = await performance_service.get_performance_metrics(period, strategy_id)
    return {
        "period": metrics.period,
        "start_date": metrics.start_date.isoformat(),
        "end_date": metrics.end_date.isoformat(),
        "total_trades": metrics.total_trades,
        "winning_trades": metrics.winning_trades,
        "losing_trades": metrics.losing_trades,
        "win_rate": round(metrics.win_rate * 100, 2),
        "total_pnl": str(metrics.total_pnl),
        "gross_profit": str(metrics.gross_profit),
        "gross_loss": str(metrics.gross_loss),
        "profit_factor": round(metrics.profit_factor, 2) if metrics.profit_factor else None,
        "average_win": str(metrics.average_win),
        "average_loss": str(metrics.average_loss),
        "largest_win": str(metrics.largest_win),
        "largest_loss": str(metrics.largest_loss),
        "average_trade": str(metrics.average_trade),
    }


@router.get("/performance/strategies")
async def get_all_strategy_performance() -> list[dict]:
    """Get performance for all strategies."""
    results = await performance_service.get_all_strategy_performance()
    return [
        {
            "strategy_id": p.strategy_id,
            "total_trades": p.total_trades,
            "winning_trades": p.winning_trades,
            "win_rate": round(p.win_rate * 100, 2),
            "total_pnl": str(p.total_pnl),
            "average_pnl": str(p.average_pnl),
            "max_drawdown": str(p.max_drawdown),
        }
        for p in results
    ]


@router.get("/trades")
async def get_trade_history(
    limit: int = Query(50, ge=1, le=500),
    strategy_id: str | None = Query(None),
) -> list[dict]:
    """Get recent trade history."""
    return await performance_service.get_trade_history(limit, strategy_id)


@router.get("/equity-curve")
async def get_equity_curve(
    days: int = Query(30, ge=1, le=365),
) -> list[dict]:
    """Get equity curve data."""
    return await performance_service.get_equity_curve(days)


@router.get("/alerts")
async def get_alerts(
    level: AlertLevel | None = Query(None),
    alert_type: AlertType | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    unacknowledged_only: bool = Query(False),
) -> list[dict]:
    """Get alerts with optional filtering."""
    alerts = alert_service.get_alerts(level, alert_type, limit, unacknowledged_only)
    return [
        {
            "id": a.id,
            "type": a.type.value,
            "level": a.level.value,
            "message": a.message,
            "timestamp": a.timestamp.isoformat(),
            "data": a.data,
            "acknowledged": a.acknowledged,
        }
        for a in alerts
    ]


@router.get("/alerts/summary")
async def get_alert_summary() -> dict:
    """Get alert summary statistics."""
    return alert_service.get_summary()


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str) -> dict:
    """Acknowledge a specific alert."""
    success = alert_service.acknowledge_alert(alert_id)
    return {"acknowledged": success, "alert_id": alert_id}


@router.post("/alerts/acknowledge-all")
async def acknowledge_all_alerts() -> dict:
    """Acknowledge all alerts."""
    count = alert_service.acknowledge_all()
    return {"acknowledged_count": count}


@router.get("/", response_class=HTMLResponse)
async def dashboard_ui() -> HTMLResponse:
    """Serve the dashboard HTML page."""
    html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TradingSystem Dashboard</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: #0f1419;
            color: #e7e9ea;
            line-height: 1.5;
        }
        .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 20px 0;
            border-bottom: 1px solid #2f3336;
            margin-bottom: 20px;
        }
        h1 { font-size: 24px; font-weight: 600; }
        .mode-badge {
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
        }
        .mode-paper { background: #1d9bf0; }
        .mode-live { background: #f91880; }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }
        .card {
            background: #16181c;
            border-radius: 16px;
            padding: 20px;
            border: 1px solid #2f3336;
        }
        .card h2 {
            font-size: 14px;
            color: #71767b;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 15px;
        }
        .metric {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #2f3336;
        }
        .metric:last-child { border-bottom: none; }
        .metric-label { color: #71767b; }
        .metric-value { font-weight: 600; font-family: 'SF Mono', monospace; }
        .positive { color: #00ba7c; }
        .negative { color: #f4212e; }
        .big-number {
            font-size: 32px;
            font-weight: 700;
            font-family: 'SF Mono', monospace;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }
        th, td {
            padding: 12px 8px;
            text-align: left;
            border-bottom: 1px solid #2f3336;
        }
        th {
            color: #71767b;
            font-weight: 500;
            text-transform: uppercase;
            font-size: 11px;
        }
        .alert-item {
            padding: 12px;
            margin-bottom: 8px;
            border-radius: 8px;
            border-left: 4px solid;
        }
        .alert-INFO { background: #1d3a5f; border-color: #1d9bf0; }
        .alert-WARNING { background: #3d2e00; border-color: #ffd400; }
        .alert-CRITICAL { background: #3d1418; border-color: #f4212e; }
        .alert-time { font-size: 11px; color: #71767b; }
        .refresh-btn {
            background: #1d9bf0;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 20px;
            cursor: pointer;
            font-weight: 600;
        }
        .refresh-btn:hover { background: #1a8cd8; }
        #lastUpdate { font-size: 12px; color: #71767b; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>TradingSystem Dashboard</h1>
            <div>
                <span id="lastUpdate"></span>
                <button class="refresh-btn" onclick="refreshAll()">Refresh</button>
                <span id="modeBadge" class="mode-badge">LOADING</span>
            </div>
        </header>

        <div class="grid">
            <div class="card">
                <h2>Account Balance</h2>
                <div class="big-number" id="balance">-</div>
                <div class="metric">
                    <span class="metric-label">NAV</span>
                    <span class="metric-value" id="nav">-</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Unrealized P&L</span>
                    <span class="metric-value" id="unrealizedPnl">-</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Margin Used</span>
                    <span class="metric-value" id="marginUsed">-</span>
                </div>
            </div>

            <div class="card">
                <h2>Today's Performance</h2>
                <div class="big-number" id="dailyPnl">-</div>
                <div class="metric">
                    <span class="metric-label">Weekly P&L</span>
                    <span class="metric-value" id="weeklyPnl">-</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Open Positions</span>
                    <span class="metric-value" id="openPositions">-</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Total Realized P&L</span>
                    <span class="metric-value" id="realizedPnl">-</span>
                </div>
            </div>

            <div class="card">
                <h2>All-Time Statistics</h2>
                <div class="metric">
                    <span class="metric-label">Total Trades</span>
                    <span class="metric-value" id="totalTrades">-</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Win Rate</span>
                    <span class="metric-value" id="winRate">-</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Profit Factor</span>
                    <span class="metric-value" id="profitFactor">-</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Average Trade</span>
                    <span class="metric-value" id="avgTrade">-</span>
                </div>
            </div>
        </div>

        <div class="grid">
            <div class="card" style="grid-column: span 2;">
                <h2>Recent Trades</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Time</th>
                            <th>Instrument</th>
                            <th>Side</th>
                            <th>Quantity</th>
                            <th>Entry</th>
                            <th>Exit</th>
                            <th>P&L</th>
                        </tr>
                    </thead>
                    <tbody id="tradesTable">
                        <tr><td colspan="7">Loading...</td></tr>
                    </tbody>
                </table>
            </div>

            <div class="card">
                <h2>Alerts</h2>
                <div id="alertsContainer">Loading...</div>
            </div>
        </div>
    </div>

    <script>
        const API_BASE = '/dashboard';

        function formatCurrency(val) {
            const num = parseFloat(val);
            return isNaN(num) ? '-' : '$' + num.toFixed(2);
        }

        function formatPnl(val) {
            const num = parseFloat(val);
            if (isNaN(num)) return '-';
            const cls = num >= 0 ? 'positive' : 'negative';
            const sign = num >= 0 ? '+' : '';
            return `<span class="${cls}">${sign}$${num.toFixed(2)}</span>`;
        }

        async function fetchPortfolio() {
            try {
                const res = await fetch(API_BASE + '/portfolio');
                const data = await res.json();

                document.getElementById('balance').innerHTML = formatCurrency(data.account_balance);
                document.getElementById('nav').innerHTML = formatCurrency(data.nav);
                document.getElementById('unrealizedPnl').innerHTML = formatPnl(data.unrealized_pnl);
                document.getElementById('marginUsed').innerHTML = formatCurrency(data.margin_used);
                document.getElementById('dailyPnl').innerHTML = formatPnl(data.daily_pnl);
                document.getElementById('weeklyPnl').innerHTML = formatPnl(data.weekly_pnl);
                document.getElementById('openPositions').textContent = data.open_positions;
                document.getElementById('realizedPnl').innerHTML = formatPnl(data.realized_pnl);
            } catch (e) {
                console.error('Failed to fetch portfolio:', e);
            }
        }

        async function fetchPerformance() {
            try {
                const res = await fetch(API_BASE + '/performance?period=all_time');
                const data = await res.json();

                document.getElementById('totalTrades').textContent = data.total_trades;
                document.getElementById('winRate').textContent = data.win_rate + '%';
                document.getElementById('profitFactor').textContent = data.profit_factor || '-';
                document.getElementById('avgTrade').innerHTML = formatPnl(data.average_trade);
            } catch (e) {
                console.error('Failed to fetch performance:', e);
            }
        }

        async function fetchTrades() {
            try {
                const res = await fetch(API_BASE + '/trades?limit=10');
                const trades = await res.json();

                const tbody = document.getElementById('tradesTable');
                if (trades.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="7">No trades yet</td></tr>';
                    return;
                }

                tbody.innerHTML = trades.map(t => `
                    <tr>
                        <td>${new Date(t.exit_time).toLocaleString()}</td>
                        <td>${t.instrument}</td>
                        <td>${t.side}</td>
                        <td>${parseFloat(t.quantity).toFixed(0)}</td>
                        <td>${parseFloat(t.entry_price).toFixed(5)}</td>
                        <td>${parseFloat(t.exit_price).toFixed(5)}</td>
                        <td>${formatPnl(t.pnl)}</td>
                    </tr>
                `).join('');
            } catch (e) {
                console.error('Failed to fetch trades:', e);
            }
        }

        async function fetchAlerts() {
            try {
                const res = await fetch(API_BASE + '/alerts?limit=10&unacknowledged_only=false');
                const alerts = await res.json();

                const container = document.getElementById('alertsContainer');
                if (alerts.length === 0) {
                    container.innerHTML = '<div style="color: #71767b;">No alerts</div>';
                    return;
                }

                container.innerHTML = alerts.map(a => `
                    <div class="alert-item alert-${a.level}">
                        <div>${a.message}</div>
                        <div class="alert-time">${new Date(a.timestamp).toLocaleString()}</div>
                    </div>
                `).join('');
            } catch (e) {
                console.error('Failed to fetch alerts:', e);
            }
        }

        async function fetchMode() {
            try {
                const res = await fetch('/');
                const data = await res.json();
                const badge = document.getElementById('modeBadge');
                badge.textContent = data.mode;
                badge.className = 'mode-badge mode-' + data.mode.toLowerCase();
            } catch (e) {
                console.error('Failed to fetch mode:', e);
            }
        }

        async function refreshAll() {
            await Promise.all([
                fetchPortfolio(),
                fetchPerformance(),
                fetchTrades(),
                fetchAlerts(),
                fetchMode()
            ]);
            document.getElementById('lastUpdate').textContent =
                'Updated: ' + new Date().toLocaleTimeString();
        }

        // Initial load
        refreshAll();

        // Auto-refresh every 30 seconds
        setInterval(refreshAll, 30000);
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html_content)
