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
        this.rateRefreshInterval = null;
        this.isConnected = false;
        this.lastRate = null;
        this.ratesWebSocket = null;
        this.wsReconnectAttempts = 0;
        this.wsMaxReconnectAttempts = 10;
        this.wsReconnectDelay = 1000;
        // Indicator state
        this.availableIndicators = [];
        this.activeIndicators = [];
        this.maxIndicators = 10;
        // Chart strategy state
        this.chartStrategies = [];
        this.availableStrategies = [];
        this.editingStrategyId = null;
        // Chart management state
        this.charts = [];
        this.activeChartId = null;
        this.indicatorColors = [
            '#58a6ff', '#f0883e', '#a371f7', '#3fb950', '#f85149',
            '#db61a2', '#79c0ff', '#d29922', '#8b949e', '#7ee787'
        ];
        // Restore saved session state
        this.restoreSessionState();
    }

    // ==================== Session Persistence ====================

    restoreSessionState() {
        try {
            const saved = localStorage.getItem('tradingSystemSession');
            if (saved) {
                const state = JSON.parse(saved);
                this.currentInstrument = state.instrument || 'EUR_USD';
                this.currentPeriod = state.period || 'M5';
                this.activeIndicators = state.indicators || [];
                this.activeChartId = state.activeChartId || null;
            }
        } catch (e) {
            console.warn('Failed to restore session from cache:', e);
        }
    }

    async restoreSessionFromAPI() {
        try {
            const session = await api.getSession();
            if (session) {
                this.currentInstrument = session.instrument || 'EUR_USD';
                this.currentPeriod = session.period || 'M5';
                this.activeChartId = session.active_chart_id || this.activeChartId;
                this.activeIndicators = (session.indicators || []).map(ind => ({
                    id: ind.id,
                    name: ind.name,
                    displayType: ind.display_type,
                    params: ind.params || {},
                    color: ind.color,
                    visible: ind.visible !== false,
                }));
                this.cacheSessionToLocalStorage();
                return true;
            }
        } catch (e) {
            console.warn('Failed to restore session from API, using cache:', e);
        }
        return false;
    }

    cacheSessionToLocalStorage() {
        try {
            const state = {
                instrument: this.currentInstrument,
                period: this.currentPeriod,
                indicators: this.activeIndicators,
                activeChartId: this.activeChartId,
            };
            localStorage.setItem('tradingSystemSession', JSON.stringify(state));
        } catch (e) {
            console.warn('Failed to cache session:', e);
        }
    }

    async saveSessionState() {
        try {
            const sessionData = {
                instrument: this.currentInstrument,
                period: this.currentPeriod,
                active_chart_id: this.activeChartId,
                indicators: this.activeIndicators.map(ind => ({
                    id: ind.id,
                    name: ind.name,
                    display_type: ind.displayType,
                    params: ind.params || {},
                    color: ind.color,
                    visible: ind.visible !== false,
                })),
            };
            await api.saveSession(sessionData);
            this.cacheSessionToLocalStorage();
        } catch (e) {
            console.warn('Failed to save session to API:', e);
            this.cacheSessionToLocalStorage();
        }
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
        // New chart button
        const newChartBtn = document.getElementById('new-chart-btn');
        if (newChartBtn) {
            newChartBtn.addEventListener('click', () => this.showNewChartModal());
        }

        // Order type toggle
        document.querySelectorAll('.order-type-btn').forEach(btn => {
            btn.addEventListener('click', (e) => this.handleOrderTypeChange(e));
        });

        // Order form submission
        const orderForm = document.getElementById('order-form');
        if (orderForm) {
            orderForm.addEventListener('submit', (e) => this.handleOrderSubmit(e));
        }

        // Sidebar toggle
        const sidebarToggle = document.getElementById('sidebar-toggle');
        if (sidebarToggle) {
            sidebarToggle.addEventListener('click', () => this.toggleSidebar());
        }

        // Panel toggles
        document.querySelectorAll('.panel-header[data-toggle="panel"]').forEach(header => {
            header.addEventListener('click', (e) => {
                const panel = header.closest('.panel');
                if (panel) {
                    panel.classList.toggle('collapsed');
                }
            });
        });

        // Indicator select
        const indicatorSelect = document.getElementById('indicator-select');
        if (indicatorSelect) {
            indicatorSelect.addEventListener('change', () => this.addSelectedIndicator());
        }

        // Auto-generate chart name when instrument/period changes in new chart modal
        const ncInstrument = document.getElementById('nc-instrument');
        const ncPeriod = document.getElementById('nc-period');
        if (ncInstrument && ncPeriod) {
            const updateName = () => {
                const nameInput = document.getElementById('nc-name');
                if (nameInput && !nameInput.dataset.userEdited) {
                    const inst = ncInstrument.value.replace('_', '/');
                    const periodLabels = {M1:'1m', M5:'5m', M15:'15m', H1:'H1', H4:'H4', D:'Daily'};
                    nameInput.value = `${inst} ${periodLabels[ncPeriod.value] || ncPeriod.value}`;
                }
            };
            ncInstrument.addEventListener('change', updateName);
            ncPeriod.addEventListener('change', updateName);
            const nameInput = document.getElementById('nc-name');
            if (nameInput) {
                nameInput.addEventListener('input', () => {
                    nameInput.dataset.userEdited = 'true';
                });
            }
        }
    }

    toggleSidebar() {
        const sidebar = document.getElementById('sidebar');
        const toggle = document.getElementById('sidebar-toggle');
        if (sidebar) {
            sidebar.classList.toggle('collapsed');
            if (toggle) {
                toggle.textContent = sidebar.classList.contains('collapsed') ? '‹' : '›';
            }
            setTimeout(() => {
                if (this.chart && this.chart.chart) {
                    this.chart.chart.applyOptions({
                        width: this.chart.container.clientWidth,
                    });
                }
            }, 350);
        }
    }

    async loadInitialData() {
        this.updateConnectionStatus(false);

        try {
            await api.getHealth();
            this.updateConnectionStatus(true);

            // Restore session from API
            await this.restoreSessionFromAPI();

            // Load charts list first
            await this.loadCharts();

            // Load data in parallel
            await Promise.all([
                this.loadAccountData(),
                this.loadChartData(),
                this.loadPositions(),
                this.loadSignals(),
            ]);

            // Load indicators and chart strategies in background
            this.loadAvailableIndicators();
            this.loadChartStrategies();

            // Restore saved indicators on chart
            if (this.activeIndicators.length > 0) {
                await this.reloadAllIndicators();
            }

            this.connectRatesWebSocket();
        } catch (error) {
            console.error('Failed to load initial data:', error);
            this.showToast('Failed to connect to server', 'error');
            this.chart.loadMockData();
        }
    }

    // ==================== Chart Management ====================

    async loadCharts() {
        try {
            this.charts = await api.getCharts();
        } catch (error) {
            console.error('Failed to load charts:', error);
            this.charts = [];
        }

        // If we have a saved activeChartId, verify it still exists
        if (this.activeChartId) {
            const exists = this.charts.find(c => c.id === this.activeChartId);
            if (!exists) {
                this.activeChartId = null;
            }
        }

        // Auto-select first chart if none selected
        if (!this.activeChartId && this.charts.length > 0) {
            this.activeChartId = this.charts[0].id;
        }

        // Apply active chart to state
        if (this.activeChartId) {
            const activeChart = this.charts.find(c => c.id === this.activeChartId);
            if (activeChart) {
                this.currentInstrument = activeChart.instrument;
                this.currentPeriod = activeChart.period;
            }
        }

        this.renderChartTabs();
    }

    renderChartTabs() {
        const container = document.getElementById('chart-tab-list');
        if (!container) return;

        if (this.charts.length === 0) {
            container.innerHTML = '<div class="chart-tabs-empty">No charts — click + to create one</div>';
            return;
        }

        const periodLabels = {M1:'1m', M5:'5m', M15:'15m', H1:'H1', H4:'H4', D:'Daily'};

        container.innerHTML = this.charts.map(c => `
            <div class="chart-tab ${c.id === this.activeChartId ? 'active' : ''}"
                 data-chart-id="${c.id}"
                 onclick="app.selectChart('${c.id}')">
                <span class="chart-tab-name">${this.escapeHtml(c.name)}</span>
                <span class="chart-tab-subtitle">${c.instrument.replace('_', '/')} · ${periodLabels[c.period] || c.period}</span>
            </div>
        `).join('');
    }

    async selectChart(chartId) {
        if (chartId === this.activeChartId) return;

        const chart = this.charts.find(c => c.id === chartId);
        if (!chart) return;

        this.activeChartId = chartId;
        this.currentInstrument = chart.instrument;
        this.currentPeriod = chart.period;

        this.renderChartTabs();
        this.saveSessionState();
        await this.loadChartData();
        this.reloadAllIndicators();
    }

    getActiveChart() {
        return this.charts.find(c => c.id === this.activeChartId) || null;
    }

    showNewChartModal() {
        const modal = document.getElementById('new-chart-modal');
        if (!modal) return;

        const form = document.getElementById('new-chart-form');
        if (form) form.reset();

        // Clear user-edited flag
        const nameInput = document.getElementById('nc-name');
        if (nameInput) {
            delete nameInput.dataset.userEdited;
            // Set default name
            const inst = document.getElementById('nc-instrument').value.replace('_', '/');
            const periodLabels = {M1:'1m', M5:'5m', M15:'15m', H1:'H1', H4:'H4', D:'Daily'};
            const period = document.getElementById('nc-period').value;
            nameInput.value = `${inst} ${periodLabels[period] || period}`;
        }

        modal.classList.remove('hidden');
    }

    hideNewChartModal() {
        const modal = document.getElementById('new-chart-modal');
        if (modal) modal.classList.add('hidden');
    }

    async handleNewChartSubmit(e) {
        e.preventDefault();

        const submitBtn = document.getElementById('nc-submit-btn');
        const originalText = submitBtn.textContent;
        submitBtn.disabled = true;
        submitBtn.textContent = 'Creating...';

        try {
            const instrument = document.getElementById('nc-instrument').value;
            const period = document.getElementById('nc-period').value;
            const name = document.getElementById('nc-name').value.trim();

            // Get or create the series
            const series = await api.getSeriesByInstrument(instrument, period);

            // Create the chart
            const newChart = await api.createChart({
                name: name,
                series_id: series.id,
            });

            this.hideNewChartModal();
            this.showToast(`Chart "${name}" created`, 'success');

            // Reload charts and select the new one
            await this.loadCharts();
            await this.selectChart(newChart.id);

        } catch (error) {
            this.showToast(error.message || 'Failed to create chart', 'error');
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = originalText;
        }
    }

    // ==================== WebSocket ====================

    connectRatesWebSocket() {
        if (this.ratesWebSocket && this.ratesWebSocket.readyState === WebSocket.OPEN) {
            return;
        }

        const wsUrl = api.getWebSocketUrl();
        console.log(`Connecting to WebSocket: ${wsUrl}`);

        try {
            this.ratesWebSocket = new WebSocket(wsUrl);

            this.ratesWebSocket.onopen = () => {
                console.log('WebSocket connected');
                this.wsReconnectAttempts = 0;
                this.showToast('Real-time rates connected', 'success');
            };

            this.ratesWebSocket.onmessage = (event) => {
                try {
                    const message = JSON.parse(event.data);
                    this.handleWebSocketMessage(message);
                } catch (e) {
                    console.error('Failed to parse WebSocket message:', e);
                }
            };

            this.ratesWebSocket.onclose = (event) => {
                console.log(`WebSocket closed: ${event.code} ${event.reason}`);
                this.handleWebSocketReconnect();
            };

            this.ratesWebSocket.onerror = (error) => {
                console.error('WebSocket error:', error);
            };
        } catch (error) {
            console.error('Failed to create WebSocket:', error);
            this.handleWebSocketReconnect();
        }
    }

    handleWebSocketMessage(message) {
        if (message.type === 'rates' && message.data) {
            const rate = message.data.find(r => r.pair === this.currentInstrument);
            if (rate) {
                this.lastRate = rate;
                this.updateRateDisplay(rate);

                if (this.chart && rate.mid) {
                    this.chart.updateCurrentPrice(rate.mid);
                }
            }
        } else if (message.type === 'error') {
            console.error('WebSocket rate error:', message.message);
        }
    }

    handleWebSocketReconnect() {
        if (this.wsReconnectAttempts >= this.wsMaxReconnectAttempts) {
            console.log('Max WebSocket reconnect attempts reached, falling back to HTTP polling');
            this.startHttpPolling();
            return;
        }

        this.wsReconnectAttempts++;
        const delay = this.wsReconnectDelay * Math.pow(2, this.wsReconnectAttempts - 1);
        console.log(`WebSocket reconnecting in ${delay}ms (attempt ${this.wsReconnectAttempts})`);

        setTimeout(() => {
            if (this.isConnected) {
                this.connectRatesWebSocket();
            }
        }, delay);
    }

    startHttpPolling() {
        if (this.rateRefreshInterval) return;

        console.log('Starting HTTP polling fallback for rates');
        this.rateRefreshInterval = setInterval(async () => {
            if (this.isConnected) {
                await this.loadCurrentRate();
            }
        }, 2000);
    }

    // ==================== Data Loading ====================

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
            if (pnl === 0) {
                pnlEl.textContent = '--';
                pnlEl.className = 'account-value';
            } else {
                pnlEl.textContent = `${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}`;
                pnlEl.className = `account-value ${pnl >= 0 ? 'positive' : 'negative'}`;
            }
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

        // Update period badge
        const periodBadge = document.getElementById('chart-period-badge');
        if (periodBadge) {
            const periodLabels = {M1:'1m', M5:'5m', M15:'15m', H1:'1H', H4:'4H', D:'1D'};
            periodBadge.textContent = periodLabels[period] || period;
        }

        await this.chart.loadData(instrument, period);
        await this.loadCurrentRate();
    }

    async loadCurrentRate() {
        try {
            const rate = await api.getCurrentRate(this.currentInstrument);
            this.lastRate = rate;
            this.updateRateDisplay(rate);

            if (this.chart && rate.mid) {
                this.chart.updateCurrentPrice(rate.mid);
            }
        } catch (error) {
            console.error('Failed to load current rate:', error);
        }
    }

    // ==================== Indicator Methods ====================

    async loadAvailableIndicators() {
        try {
            const data = await api.getAvailableIndicators();

            const commonIndicators = new Set([
                'sma', 'ema', 'wma', 'bbands', 'vwap', 'kc', 'dema', 'tema',
                'ichimoku', 'supertrend', 'psar',
                'rsi', 'macd', 'stoch', 'stochrsi', 'cci', 'mfi', 'willr',
                'atr', 'adx', 'aroon', 'ao', 'obv', 'cmf', 'mom', 'roc',
            ]);

            const allIndicators = [
                ...(data.custom || []),
                ...(data.pandas_ta || [])
            ];

            this.availableIndicators = allIndicators
                .filter(i => commonIndicators.has(i.name.toLowerCase()))
                .sort((a, b) => a.name.localeCompare(b.name));

            this.populateIndicatorSelect();
        } catch (error) {
            console.error('Failed to load indicators:', error);
        }
    }

    populateIndicatorSelect() {
        const select = document.getElementById('indicator-select');
        if (!select) return;

        select.innerHTML = '<option value="">Select indicator...</option>';

        const overlayIndicators = this.availableIndicators.filter(i => i.display_type === 'overlay');
        const paneIndicators = this.availableIndicators.filter(i => i.display_type === 'pane');

        if (overlayIndicators.length > 0) {
            const overlayGroup = document.createElement('optgroup');
            overlayGroup.label = 'Overlay (on price)';
            overlayIndicators.forEach(ind => {
                const option = document.createElement('option');
                option.value = ind.name;
                option.textContent = ind.name.toUpperCase();
                option.dataset.displayType = 'overlay';
                overlayGroup.appendChild(option);
            });
            select.appendChild(overlayGroup);
        }

        if (paneIndicators.length > 0) {
            const paneGroup = document.createElement('optgroup');
            paneGroup.label = 'Pane (below chart)';
            paneIndicators.forEach(ind => {
                const option = document.createElement('option');
                option.value = ind.name;
                option.textContent = ind.name.toUpperCase();
                option.dataset.displayType = 'pane';
                paneGroup.appendChild(option);
            });
            select.appendChild(paneGroup);
        }
    }

    async addSelectedIndicator() {
        const select = document.getElementById('indicator-select');
        if (!select || !select.value) return;

        const indicatorName = select.value;
        const selectedOption = select.options[select.selectedIndex];
        const displayType = selectedOption.dataset.displayType || 'pane';

        if (this.activeIndicators.find(i => i.name === indicatorName)) {
            this.showToast(`${indicatorName.toUpperCase()} already added`, 'warning');
            return;
        }

        if (this.activeIndicators.length >= this.maxIndicators) {
            this.showToast(`Maximum ${this.maxIndicators} indicators allowed`, 'warning');
            return;
        }

        let params = {};
        try {
            const info = await api.getIndicatorInfo(indicatorName);
            params = info.default_params || {};
        } catch (error) {
            console.log('Using empty params for', indicatorName);
        }

        const colorIndex = this.activeIndicators.length % this.indicatorColors.length;
        const color = this.indicatorColors[colorIndex];

        const indicator = {
            id: Date.now(),
            name: indicatorName,
            displayType: displayType,
            params: params,
            color: color,
            visible: true,
        };
        this.activeIndicators.push(indicator);

        select.value = '';
        this.updateIndicatorCount();
        this.renderActiveIndicators();
        this.saveSessionState();

        await this.calculateAndRenderIndicator(indicator);
    }

    async removeIndicator(indicatorId) {
        const index = this.activeIndicators.findIndex(i => i.id === indicatorId);
        if (index === -1) return;

        if (this.chart) {
            this.chart.removeIndicator(indicatorId);
        }

        this.activeIndicators.splice(index, 1);
        this.updateIndicatorCount();
        this.renderActiveIndicators();
        this.saveSessionState();
    }

    toggleIndicatorVisibility(indicatorId) {
        const indicator = this.activeIndicators.find(i => i.id === indicatorId);
        if (!indicator) return;

        indicator.visible = !indicator.visible;
        if (this.chart) {
            this.chart.setIndicatorVisible(indicator.id, indicator.visible);
        }
        this.renderActiveIndicators();
    }

    updateIndicatorCount() {
        const countEl = document.getElementById('indicator-count');
        if (countEl) {
            countEl.textContent = `${this.activeIndicators.length}/${this.maxIndicators}`;
        }
    }

    renderActiveIndicators() {
        const container = document.getElementById('active-indicators');
        if (!container) return;

        if (this.activeIndicators.length === 0) {
            container.innerHTML = '<div class="empty-state">No indicators added</div>';
            return;
        }

        container.innerHTML = this.activeIndicators.map(ind => `
            <div class="indicator-item" data-id="${ind.id}">
                <div class="indicator-item-info">
                    <div class="indicator-item-color" style="background: ${ind.color}"></div>
                    <span class="indicator-item-name">${ind.name.toUpperCase()}</span>
                    <span class="indicator-item-type">${ind.displayType}</span>
                </div>
                <div class="indicator-item-actions">
                    <button class="indicator-item-btn visibility"
                            onclick="app.toggleIndicatorVisibility(${ind.id})"
                            title="${ind.visible ? 'Hide' : 'Show'}">
                        ${ind.visible ? '👁' : '👁‍🗨'}
                    </button>
                    <button class="indicator-item-btn remove"
                            onclick="app.removeIndicator(${ind.id})"
                            title="Remove">×</button>
                </div>
            </div>
        `).join('');
    }

    async calculateAndRenderIndicator(indicator) {
        try {
            const result = await api.calculateIndicator(
                this.currentInstrument,
                this.currentPeriod,
                indicator.name,
                indicator.params,
                500
            );

            if (this.chart && result.values && result.values.length > 0) {
                this.chart.addIndicator(indicator, result.values);
            }
        } catch (error) {
            console.error(`Failed to calculate indicator ${indicator.name}:`, error.message);
            this.showToast(`Failed to load ${indicator.name.toUpperCase()}: ${error.message}`, 'error');
        }
    }

    async reloadAllIndicators() {
        for (const indicator of this.activeIndicators) {
            await this.calculateAndRenderIndicator(indicator);
        }
    }

    // ==================== Chart Strategy Methods ====================

    async loadChartStrategies() {
        try {
            this.chartStrategies = await api.getChartStrategies();
            this.renderChartStrategies();

            this.availableStrategies = await api.getAvailableStrategies();
            this.populateStrategySelect();
        } catch (error) {
            console.error('Failed to load chart strategies:', error);
            this.chartStrategies = [];
            this.renderChartStrategies();
        }
    }

    populateStrategySelect() {
        const select = document.getElementById('si-strategy');
        if (!select) return;

        select.innerHTML = '<option value="">Select strategy...</option>';

        const seen = new Set();
        const uniqueStrategies = this.availableStrategies.filter(s => {
            if (seen.has(s.id)) return false;
            seen.add(s.id);
            return true;
        });

        uniqueStrategies.forEach(strategy => {
            const option = document.createElement('option');
            option.value = strategy.id;
            option.textContent = strategy.name;
            option.title = strategy.description;
            select.appendChild(option);
        });
    }

    renderChartStrategies() {
        const container = document.getElementById('strategy-instances-container');
        const countEl = document.getElementById('strategy-instance-count');

        if (countEl) {
            countEl.textContent = this.chartStrategies.length;
        }

        if (!container) return;

        if (this.chartStrategies.length === 0) {
            container.innerHTML = '<div class="empty-state">No chart strategies</div>';
            return;
        }

        container.innerHTML = this.chartStrategies.map(cs => `
            <div class="strategy-instance-item ${cs.enabled ? '' : 'disabled'}" data-id="${cs.id}">
                <div class="si-header">
                    <span class="si-name">${this.escapeHtml(cs.strategy_id)}</span>
                    <span class="si-status ${cs.enabled ? 'active' : 'inactive'}">${cs.enabled ? '●' : '○'}</span>
                </div>
                <div class="si-details">
                    <span class="si-strategy">${cs.strategy_id}</span>
                    <span class="si-chart-id" title="${cs.chart_id}">Chart</span>
                </div>
                <div class="si-actions">
                    <button class="si-btn toggle" onclick="app.toggleChartStrategy('${cs.id}')" title="${cs.enabled ? 'Disable' : 'Enable'}">
                        ${cs.enabled ? '⏸' : '▶'}
                    </button>
                    <button class="si-btn backtest" onclick="app.runChartStrategyBacktest('${cs.id}')" title="Run Backtest">📊</button>
                    <button class="si-btn edit" onclick="app.editChartStrategy('${cs.id}')" title="Edit">✏️</button>
                    <button class="si-btn delete" onclick="app.deleteChartStrategy('${cs.id}')" title="Delete">🗑</button>
                </div>
            </div>
        `).join('');
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    async showChartStrategyModal(csId = null) {
        const modal = document.getElementById('strategy-modal');
        const title = document.getElementById('strategy-modal-title');
        const submitBtn = document.getElementById('si-submit-btn');
        const form = document.getElementById('strategy-instance-form');

        if (!modal || !form) return;

        await this.populateChartSelect();

        this.editingStrategyId = csId;

        if (csId) {
            const cs = this.chartStrategies.find(i => i.id === csId);
            if (!cs) return;

            title.textContent = 'Edit Chart Strategy';
            submitBtn.textContent = 'Save';

            document.getElementById('si-id').value = cs.id;
            document.getElementById('si-strategy').value = cs.strategy_id;
            document.getElementById('si-strategy').disabled = true;
            document.getElementById('si-chart-id').value = cs.chart_id;
            document.getElementById('si-chart-id').disabled = true;
            document.getElementById('si-params').value = JSON.stringify(cs.parameters, null, 2);
            document.getElementById('si-enabled').checked = cs.enabled;
        } else {
            title.textContent = 'New Chart Strategy';
            submitBtn.textContent = 'Create';
            form.reset();
            document.getElementById('si-id').value = '';
            document.getElementById('si-strategy').disabled = false;
            document.getElementById('si-chart-id').disabled = false;
            document.getElementById('si-enabled').checked = false;
        }

        modal.classList.remove('hidden');
    }

    async populateChartSelect() {
        const select = document.getElementById('si-chart-id');
        if (!select) return;

        select.innerHTML = '<option value="">Select chart...</option>';

        try {
            const charts = await api.getCharts();
            charts.forEach(chart => {
                const option = document.createElement('option');
                option.value = chart.id;
                const subtitle = chart.instrument ? ` (${chart.instrument.replace('_','/')} · ${chart.period})` : '';
                option.textContent = chart.name + subtitle;
                select.appendChild(option);
            });
        } catch (error) {
            console.error('Failed to load charts:', error);
        }
    }

    hideChartStrategyModal() {
        const modal = document.getElementById('strategy-modal');
        if (modal) {
            modal.classList.add('hidden');
        }
        this.editingStrategyId = null;
    }

    async handleChartStrategySubmit(e) {
        e.preventDefault();

        const submitBtn = document.getElementById('si-submit-btn');
        const originalText = submitBtn.textContent;
        submitBtn.disabled = true;
        submitBtn.textContent = 'Saving...';

        try {
            const strategyId = document.getElementById('si-strategy').value;
            const chartId = document.getElementById('si-chart-id').value;
            const paramsStr = document.getElementById('si-params').value.trim();
            const enabled = document.getElementById('si-enabled').checked;

            let parameters = {};
            if (paramsStr) {
                try {
                    parameters = JSON.parse(paramsStr);
                } catch (err) {
                    this.showToast('Invalid JSON in parameters', 'error');
                    return;
                }
            }

            if (this.editingStrategyId) {
                await api.updateChartStrategy(this.editingStrategyId, {
                    parameters,
                    enabled,
                });
                this.showToast('Chart strategy updated', 'success');
            } else {
                await api.createChartStrategy({
                    chart_id: chartId,
                    strategy_id: strategyId,
                    parameters,
                    enabled,
                });
                this.showToast('Chart strategy created', 'success');
            }

            this.hideChartStrategyModal();
            await this.loadChartStrategies();

        } catch (error) {
            this.showToast(error.message || 'Failed to save chart strategy', 'error');
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = originalText;
        }
    }

    editChartStrategy(csId) {
        this.showChartStrategyModal(csId);
    }

    async toggleChartStrategy(csId) {
        try {
            await api.toggleChartStrategy(csId);
            await this.loadChartStrategies();
        } catch (error) {
            this.showToast(error.message || 'Failed to toggle chart strategy', 'error');
        }
    }

    async deleteChartStrategy(csId) {
        const cs = this.chartStrategies.find(i => i.id === csId);
        if (!cs) return;

        if (!confirm(`Delete strategy "${cs.strategy_id}"? This cannot be undone.`)) return;

        try {
            await api.deleteChartStrategy(csId);
            this.showToast('Chart strategy deleted', 'success');
            await this.loadChartStrategies();
        } catch (error) {
            this.showToast(error.message || 'Failed to delete chart strategy', 'error');
        }
    }

    async runChartStrategyBacktest(csId) {
        const cs = this.chartStrategies.find(i => i.id === csId);
        if (!cs) return;

        this.showToast(`Running backtest for "${cs.strategy_id}"...`, 'info');

        try {
            const result = await api.runChartStrategyBacktest(csId, 30);
            const metrics = result.result?.metrics || {};

            const trades = metrics.total_trades || 0;
            const returnPct = parseFloat(metrics.total_return_pct || 0).toFixed(2);
            const winRate = (metrics.win_rate * 100 || 0).toFixed(1);

            this.showToast(
                `Backtest complete: ${trades} trades, ${returnPct}% return, ${winRate}% win rate`,
                trades > 0 ? 'success' : 'info'
            );
        } catch (error) {
            this.showToast(error.message || 'Backtest failed', 'error');
        }
    }

    // ==================== Display Updates ====================

    updateRateDisplay(rate) {
        const priceEl = document.getElementById('chart-price');
        const changeEl = document.getElementById('chart-change');
        const bidEl = document.getElementById('chart-bid');
        const askEl = document.getElementById('chart-ask');
        const spreadEl = document.getElementById('chart-spread');

        if (priceEl && rate.mid) {
            priceEl.textContent = rate.mid;
        }

        if (bidEl && rate.bid) {
            bidEl.textContent = rate.bid;
        }
        if (askEl && rate.ask) {
            askEl.textContent = rate.ask;
        }
        if (spreadEl && rate.spread) {
            spreadEl.textContent = rate.spread;
        }

        if (changeEl) {
            if (rate.tradeable === false) {
                changeEl.textContent = 'Market Closed';
                changeEl.className = 'chart-change muted';
            } else if (rate.age_seconds !== undefined && rate.age_seconds > 30) {
                changeEl.textContent = `(${rate.age_seconds.toFixed(0)}s stale)`;
                changeEl.className = 'chart-change negative';
            } else if (rate.spread) {
                const spreadPips = (parseFloat(rate.spread) * 10000).toFixed(1);
                changeEl.innerHTML = `<span class="spread-icon">↔</span> ${spreadPips}`;
                changeEl.className = 'chart-change';
            }
        }
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

    // ==================== Order Handling ====================

    handleOrderTypeChange(e) {
        const btn = e.currentTarget;
        const side = btn.dataset.side;

        document.querySelectorAll('.order-type-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');

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
            const riskCheck = await api.checkTradeRisk(this.currentInstrument, this.orderSide, quantity);

            if (!riskCheck.approved) {
                this.showToast(`Risk check failed: ${riskCheck.messages.join(', ')}`, 'error');
                return;
            }

            const result = await api.executeTrade(
                this.currentInstrument,
                this.orderSide,
                quantity,
                stopLoss ? parseFloat(stopLoss) : null,
                takeProfit ? parseFloat(takeProfit) : null
            );

            this.showToast(result.message || 'Order placed successfully', 'success');

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

            await Promise.all([
                this.loadPositions(),
                this.loadAccountData(),
            ]);
        } catch (error) {
            this.showToast(error.message || 'Failed to close position', 'error');
        }
    }

    // ==================== Utility ====================

    updateConnectionStatus(connected) {
        this.isConnected = connected;
        const connectionStatus = document.getElementById('connection-status');

        if (connectionStatus) {
            connectionStatus.className = `connection-status ${connected ? 'connected' : ''}`;
            connectionStatus.title = connected ? 'Connected' : 'Disconnected';
        }
    }

    startAutoRefresh() {
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
        if (this.rateRefreshInterval) {
            clearInterval(this.rateRefreshInterval);
            this.rateRefreshInterval = null;
        }
    }

    disconnectRatesWebSocket() {
        if (this.ratesWebSocket) {
            this.ratesWebSocket.close();
            this.ratesWebSocket = null;
        }
    }

    showToast(message, type = 'info') {
        const container = document.getElementById('toast-container');
        if (!container) return;

        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `<span class="toast-message">${message}</span>`;

        container.appendChild(toast);

        setTimeout(() => {
            toast.style.animation = 'slideIn 0.3s ease reverse';
            setTimeout(() => toast.remove(), 300);
        }, 5000);
    }

    destroy() {
        this.stopAutoRefresh();
        this.disconnectRatesWebSocket();
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
