/**
 * TradingSystem Dashboard Application
 * Main application logic
 */

class TradingApp {
    constructor() {
        this.chart = null;
        this.currentInstrument = 'EUR_USD';
        this.currentPeriod = 'M5';
        this.orderSide = 'BUY';
        this.positions = [];
        this.signals = [];
        this.refreshInterval = null;
        this.isConnected = false;
    }

    async init() {
        console.log('Initializing TradingSystem Dashboard...');

        // Initialize chart
        this.chart = new ChartManager('chart');
        this.chart.init();

        // Setup event listeners
        this.setupEventListeners();

        // Load initial data
        await this.loadInitialData();

        // Start auto-refresh
        this.startAutoRefresh();

        console.log('Dashboard initialized');
    }

    setupEventListeners() {
        // Instrument tabs
        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', (e) => this.handleInstrumentChange(e));
        });

        // Timeframe buttons
        document.querySelectorAll('.tf-btn').forEach(btn => {
            btn.addEventListener('click', (e) => this.handleTimeframeChange(e));
        });

        // Order type toggle
        document.querySelectorAll('.order-type-btn').forEach(btn => {
            btn.addEventListener('click', (e) => this.handleOrderTypeChange(e));
        });

        // Order form submission
        const orderForm = document.getElementById('order-form');
        if (orderForm) {
            orderForm.addEventListener('submit', (e) => this.handleOrderSubmit(e));
        }
    }

    async loadInitialData() {
        // Show loading state
        this.updateConnectionStatus(false);

        try {
            // Check API health
            await api.getHealth();
            this.updateConnectionStatus(true);

            // Load data in parallel
            await Promise.all([
                this.loadAccountData(),
                this.loadChartData(),
                this.loadPositions(),
                this.loadSignals(),
            ]);
        } catch (error) {
            console.error('Failed to load initial data:', error);
            this.showToast('Failed to connect to server', 'error');

            // Load mock data for chart
            this.chart.loadMockData();
        }
    }

    async loadAccountData() {
        try {
            const account = await api.getAccountSummary();
            this.updateAccountDisplay(account);
        } catch (error) {
            console.error('Failed to load account data:', error);
            this.updateAccountDisplay(null);
        }
    }

    updateAccountDisplay(account) {
        const balanceEl = document.getElementById('account-balance');
        const pnlEl = document.getElementById('account-pnl');
        const dailyPnlEl = document.getElementById('daily-pnl');
        const marginEl = document.getElementById('margin-used');

        if (!account) {
            if (balanceEl) balanceEl.textContent = '--';
            if (pnlEl) pnlEl.textContent = '--';
            if (dailyPnlEl) dailyPnlEl.textContent = '--';
            if (marginEl) marginEl.textContent = '--';
            return;
        }

        if (balanceEl) {
            balanceEl.textContent = `$${parseFloat(account.balance).toLocaleString('en-US', { minimumFractionDigits: 2 })}`;
        }

        if (pnlEl) {
            const pnl = parseFloat(account.unrealized_pnl);
            pnlEl.textContent = `${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}`;
            pnlEl.className = `account-value ${pnl >= 0 ? 'positive' : 'negative'}`;
        }

        if (marginEl) {
            marginEl.textContent = `$${parseFloat(account.margin_used).toLocaleString('en-US', { minimumFractionDigits: 2 })}`;
        }
    }

    async loadChartData() {
        const instrument = this.currentInstrument;
        const period = this.currentPeriod;

        // Update chart title
        const titleEl = document.getElementById('chart-title');
        if (titleEl) {
            titleEl.textContent = instrument.replace('_', '/');
        }

        await this.chart.loadData(instrument, period);
    }

    async loadPositions() {
        try {
            const positions = await api.getPositions('OPEN');
            this.positions = positions || [];
            this.renderPositions();
        } catch (error) {
            console.error('Failed to load positions:', error);
            this.positions = [];
            this.renderPositions();
        }
    }

    renderPositions() {
        const container = document.getElementById('positions-container');
        if (!container) return;

        if (this.positions.length === 0) {
            container.innerHTML = '<div class="empty-state">No open positions</div>';
            return;
        }

        container.innerHTML = this.positions.map(pos => `
            <div class="position-card" data-position-id="${pos.id}">
                <div class="position-header">
                    <span class="position-instrument">${pos.instrument.replace('_', '/')}</span>
                    <span class="position-side ${pos.side.toLowerCase()}">${pos.side}</span>
                </div>
                <div class="position-details">
                    <div class="position-detail">
                        <span class="position-detail-label">Quantity</span>
                        <span class="position-detail-value">${parseFloat(pos.quantity).toLocaleString()}</span>
                    </div>
                    <div class="position-detail position-pnl">
                        <span class="position-detail-label">P&L</span>
                        <span class="position-detail-value ${parseFloat(pos.pnl || 0) >= 0 ? 'positive' : 'negative'}">
                            ${parseFloat(pos.pnl || 0) >= 0 ? '+' : ''}$${parseFloat(pos.pnl || 0).toFixed(2)}
                        </span>
                    </div>
                    <div class="position-detail">
                        <span class="position-detail-label">Entry</span>
                        <span class="position-detail-value">${parseFloat(pos.entry_price).toFixed(5)}</span>
                    </div>
                    <div class="position-detail">
                        <span class="position-detail-label">Current</span>
                        <span class="position-detail-value">${parseFloat(pos.current_price || pos.entry_price).toFixed(5)}</span>
                    </div>
                </div>
                <div class="position-actions">
                    <button class="position-btn close" onclick="app.closePosition('${pos.id}')">Close</button>
                </div>
            </div>
        `).join('');

        // Update positions count
        const countEl = document.getElementById('positions-count');
        if (countEl) {
            countEl.textContent = `${this.positions.length} open`;
        }
    }

    async loadSignals() {
        try {
            const signals = await api.getLatestSignals(null, 5);
            this.signals = signals || [];
            this.renderSignals();
        } catch (error) {
            console.error('Failed to load signals:', error);
            this.signals = [];
            this.renderSignals();
        }
    }

    renderSignals() {
        const container = document.getElementById('signals-container');
        if (!container) return;

        if (this.signals.length === 0) {
            container.innerHTML = '<div class="empty-state">No recent signals</div>';
            return;
        }

        container.innerHTML = this.signals.map(signal => {
            const isBuy = signal.signal_type === 'BUY';
            const timeAgo = this.getTimeAgo(signal.time);

            return `
                <div class="signal-item">
                    <div class="signal-icon ${isBuy ? 'buy' : 'sell'}">${isBuy ? '↑' : '↓'}</div>
                    <div class="signal-info">
                        <div class="signal-title">${signal.strategy_id} - ${signal.signal_type}</div>
                        <div class="signal-meta">${signal.instrument.replace('_', '/')} • ${timeAgo}</div>
                    </div>
                    <div class="signal-strength ${isBuy ? 'positive' : 'negative'}">${parseFloat(signal.strength).toFixed(2)}</div>
                </div>
            `;
        }).join('');
    }

    getTimeAgo(timestamp) {
        const now = new Date();
        const time = new Date(timestamp);
        const diffMs = now - time;
        const diffMins = Math.floor(diffMs / 60000);

        if (diffMins < 1) return 'Just now';
        if (diffMins < 60) return `${diffMins} min ago`;

        const diffHours = Math.floor(diffMins / 60);
        if (diffHours < 24) return `${diffHours}h ago`;

        const diffDays = Math.floor(diffHours / 24);
        return `${diffDays}d ago`;
    }

    handleInstrumentChange(e) {
        const tab = e.currentTarget;
        const instrument = tab.dataset.instrument;

        if (!instrument || instrument === this.currentInstrument) return;

        // Update UI
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');

        // Update state and reload chart
        this.currentInstrument = instrument;
        this.loadChartData();
    }

    handleTimeframeChange(e) {
        const btn = e.currentTarget;
        const period = btn.dataset.period;

        if (!period || period === this.currentPeriod) return;

        // Update UI
        document.querySelectorAll('.tf-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');

        // Update state and reload chart
        this.currentPeriod = period;
        this.loadChartData();
    }

    handleOrderTypeChange(e) {
        const btn = e.currentTarget;
        const side = btn.dataset.side;

        // Update UI
        document.querySelectorAll('.order-type-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');

        // Update submit button
        const submitBtn = document.getElementById('submit-order-btn');
        if (submitBtn) {
            submitBtn.textContent = `Place ${side} Order`;
            submitBtn.className = `submit-btn ${side.toLowerCase()}`;
        }

        this.orderSide = side;
    }

    async handleOrderSubmit(e) {
        e.preventDefault();

        const quantity = document.getElementById('order-quantity')?.value;
        const stopLoss = document.getElementById('order-stop-loss')?.value || null;
        const takeProfit = document.getElementById('order-take-profit')?.value || null;

        if (!quantity || parseFloat(quantity) <= 0) {
            this.showToast('Please enter a valid quantity', 'warning');
            return;
        }

        const submitBtn = document.getElementById('submit-order-btn');
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = 'Placing Order...';
        }

        try {
            // First check risk
            const riskCheck = await api.checkTradeRisk(this.currentInstrument, this.orderSide, quantity);

            if (!riskCheck.approved) {
                this.showToast(`Risk check failed: ${riskCheck.messages.join(', ')}`, 'error');
                return;
            }

            // Execute trade
            const result = await api.executeTrade(
                this.currentInstrument,
                this.orderSide,
                quantity,
                stopLoss ? parseFloat(stopLoss) : null,
                takeProfit ? parseFloat(takeProfit) : null
            );

            this.showToast(result.message || 'Order placed successfully', 'success');

            // Refresh positions and account
            await Promise.all([
                this.loadPositions(),
                this.loadAccountData(),
            ]);

        } catch (error) {
            this.showToast(error.message || 'Failed to place order', 'error');
        } finally {
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = `Place ${this.orderSide} Order`;
            }
        }
    }

    async closePosition(positionId) {
        if (!confirm('Are you sure you want to close this position?')) return;

        try {
            await api.closeTrade(positionId);
            this.showToast('Position closed successfully', 'success');

            // Refresh positions and account
            await Promise.all([
                this.loadPositions(),
                this.loadAccountData(),
            ]);
        } catch (error) {
            this.showToast(error.message || 'Failed to close position', 'error');
        }
    }

    updateConnectionStatus(connected) {
        this.isConnected = connected;
        const statusDot = document.getElementById('status-dot');
        const statusText = document.getElementById('status-text');

        if (statusDot) {
            statusDot.className = `status-dot ${connected ? 'connected' : ''}`;
        }
        if (statusText) {
            statusText.textContent = connected ? 'Connected' : 'Disconnected';
        }
    }

    startAutoRefresh() {
        // Refresh positions and account every 10 seconds
        this.refreshInterval = setInterval(async () => {
            if (this.isConnected) {
                await Promise.all([
                    this.loadAccountData(),
                    this.loadPositions(),
                ]);
            }
        }, 10000);
    }

    stopAutoRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
            this.refreshInterval = null;
        }
    }

    showToast(message, type = 'info') {
        const container = document.getElementById('toast-container');
        if (!container) return;

        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `<span class="toast-message">${message}</span>`;

        container.appendChild(toast);

        // Remove after 5 seconds
        setTimeout(() => {
            toast.style.animation = 'slideIn 0.3s ease reverse';
            setTimeout(() => toast.remove(), 300);
        }, 5000);
    }

    destroy() {
        this.stopAutoRefresh();
        if (this.chart) {
            this.chart.destroy();
        }
    }
}

// Initialize app when DOM is ready
let app;
document.addEventListener('DOMContentLoaded', () => {
    app = new TradingApp();
    app.init();
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (app) {
        app.destroy();
    }
});
