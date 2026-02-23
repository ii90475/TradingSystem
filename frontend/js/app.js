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
        // Strategy instance state
        this.strategyInstances = [];
        this.availableStrategies = [];
        this.editingInstanceId = null;
        this.indicatorColors = [
            '#58a6ff', '#f0883e', '#a371f7', '#3fb950', '#f85149',
            '#db61a2', '#79c0ff', '#d29922', '#8b949e', '#7ee787'
        ];
        // Restore saved session state
        this.restoreSessionState();
    }

    // ==================== Session Persistence ====================

    restoreSessionState() {
        // First try localStorage for fast initial load (will be updated from API later)
        try {
            const saved = localStorage.getItem('tradingSystemSession');
            if (saved) {
                const state = JSON.parse(saved);
                this.currentInstrument = state.instrument || 'EUR_USD';
                this.currentPeriod = state.period || 'M5';
                this.activeIndicators = state.indicators || [];
                console.log('Restored session from cache:', this.currentInstrument, this.currentPeriod, this.activeIndicators.length, 'indicators');
            }
        } catch (e) {
            console.warn('Failed to restore session from cache:', e);
        }
    }

    async restoreSessionFromAPI() {
        // Fetch from API (source of truth) and update local state
        try {
            const session = await api.getSession();
            if (session) {
                this.currentInstrument = session.instrument || 'EUR_USD';
                this.currentPeriod = session.period || 'M5';
                // Map API format to frontend format
                this.activeIndicators = (session.indicators || []).map(ind => ({
                    id: ind.id,
                    name: ind.name,
                    displayType: ind.display_type,
                    params: ind.params || {},
                    color: ind.color,
                    visible: ind.visible !== false,
                }));
                console.log('Restored session from API:', this.currentInstrument, this.currentPeriod, this.activeIndicators.length, 'indicators');
                // Cache to localStorage
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
            };
            localStorage.setItem('tradingSystemSession', JSON.stringify(state));
        } catch (e) {
            console.warn('Failed to cache session:', e);
        }
    }

    async saveSessionState() {
        // Save to API (source of truth)
        try {
            const sessionData = {
                instrument: this.currentInstrument,
                period: this.currentPeriod,
                // Map frontend format to API format
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
            // Also cache to localStorage for fast reload
            this.cacheSessionToLocalStorage();
        } catch (e) {
            console.warn('Failed to save session to API:', e);
            // Still cache locally as fallback
            this.cacheSessionToLocalStorage();
        }
    }

    async init() {
        console.log('Initializing TradingSystem Dashboard...');

        // Initialize chart
        this.chart = new ChartManager('chart');
        this.chart.init();

        // Apply restored session state to UI
        this.applySessionStateToUI();

        // Setup event listeners
        this.setupEventListeners();

        // Load initial data
        await this.loadInitialData();

        // Start auto-refresh
        this.startAutoRefresh();

        console.log('Dashboard initialized');
    }

    applySessionStateToUI() {
        // Update instrument tabs
        document.querySelectorAll('.tab').forEach(tab => {
            tab.classList.toggle('active', tab.dataset.instrument === this.currentInstrument);
        });

        // Update timeframe buttons
        document.querySelectorAll('.tf-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.period === this.currentPeriod);
        });

        // Update indicator count
        this.updateIndicatorCount();
        this.renderActiveIndicators();
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

        // Indicator select - add on change (no + button needed)
        const indicatorSelect = document.getElementById('indicator-select');
        if (indicatorSelect) {
            indicatorSelect.addEventListener('change', () => this.addSelectedIndicator());
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
            // Trigger chart resize after transition
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
        // Show loading state
        this.updateConnectionStatus(false);

        try {
            // Check API health
            await api.getHealth();
            this.updateConnectionStatus(true);

            // Restore session from API (source of truth)
            const apiRestored = await this.restoreSessionFromAPI();
            if (apiRestored) {
                // Update UI with restored state
                this.applySessionStateToUI();
            }

            // Load data in parallel
            await Promise.all([
                this.loadAccountData(),
                this.loadChartData(),
                this.loadPositions(),
                this.loadSignals(),
            ]);

            // Load indicators and strategy instances in background (non-blocking)
            this.loadAvailableIndicators();
            this.loadStrategyInstances();

            // Restore saved indicators on chart
            if (this.activeIndicators.length > 0) {
                console.log('Restoring', this.activeIndicators.length, 'saved indicators');
                await this.reloadAllIndicators();
            }

            // Connect to WebSocket for real-time rates
            this.connectRatesWebSocket();
        } catch (error) {
            console.error('Failed to load initial data:', error);
            this.showToast('Failed to connect to server', 'error');

            // Load mock data for chart
            this.chart.loadMockData();
        }
    }

    connectRatesWebSocket() {
        if (this.ratesWebSocket && this.ratesWebSocket.readyState === WebSocket.OPEN) {
            return; // Already connected
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
            // Find rate for current instrument
            const rate = message.data.find(r => r.pair === this.currentInstrument);
            if (rate) {
                this.lastRate = rate;
                this.updateRateDisplay(rate);

                // Update chart's current price line
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
        // Fallback to HTTP polling if WebSocket fails
        if (this.rateRefreshInterval) return;

        console.log('Starting HTTP polling fallback for rates');
        this.rateRefreshInterval = setInterval(async () => {
            if (this.isConnected) {
                await this.loadCurrentRate();
            }
        }, 2000);
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

        await this.chart.loadData(instrument, period);

        // Also load current rate for real-time price
        await this.loadCurrentRate();
    }

    async loadCurrentRate() {
        try {
            const rate = await api.getCurrentRate(this.currentInstrument);
            this.lastRate = rate;
            this.updateRateDisplay(rate);

            // Update chart's current price line
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

            // Limit to most common/useful indicators for performance
            const commonIndicators = new Set([
                // Overlay (on price)
                'sma', 'ema', 'wma', 'bbands', 'vwap', 'kc', 'dema', 'tema',
                'ichimoku', 'supertrend', 'psar',
                // Pane (below chart)
                'rsi', 'macd', 'stoch', 'stochrsi', 'cci', 'mfi', 'willr',
                'atr', 'adx', 'aroon', 'ao', 'obv', 'cmf', 'mom', 'roc',
            ]);

            // Combine and filter to common indicators only
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

        // Clear existing options except the first
        select.innerHTML = '<option value="">Select indicator...</option>';

        // Group indicators by type
        const overlayIndicators = this.availableIndicators.filter(i => i.display_type === 'overlay');
        const paneIndicators = this.availableIndicators.filter(i => i.display_type === 'pane');

        // Add overlay group
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

        // Add pane group
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

        // Check if already added
        if (this.activeIndicators.find(i => i.name === indicatorName)) {
            this.showToast(`${indicatorName.toUpperCase()} already added`, 'warning');
            return;
        }

        // Check max limit
        if (this.activeIndicators.length >= this.maxIndicators) {
            this.showToast(`Maximum ${this.maxIndicators} indicators allowed`, 'warning');
            return;
        }

        // Get indicator info for default params
        let params = {};
        try {
            const info = await api.getIndicatorInfo(indicatorName);
            params = info.default_params || {};
        } catch (error) {
            console.log('Using empty params for', indicatorName);
        }

        // Assign color
        const colorIndex = this.activeIndicators.length % this.indicatorColors.length;
        const color = this.indicatorColors[colorIndex];

        // Add to active list
        const indicator = {
            id: Date.now(),
            name: indicatorName,
            displayType: displayType,
            params: params,
            color: color,
            visible: true,
        };
        this.activeIndicators.push(indicator);

        // Reset select
        select.value = '';
        this.updateIndicatorCount();
        this.renderActiveIndicators();
        this.saveSessionState();

        // Calculate and render on chart
        await this.calculateAndRenderIndicator(indicator);
    }

    async removeIndicator(indicatorId) {
        const index = this.activeIndicators.findIndex(i => i.id === indicatorId);
        if (index === -1) return;

        const indicator = this.activeIndicators[index];

        // Remove from chart
        if (this.chart) {
            this.chart.removeIndicator(indicator.id);
        }

        // Remove from list
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
            console.log(`Calculating indicator ${indicator.name} for ${this.currentInstrument}/${this.currentPeriod}`);
            const result = await api.calculateIndicator(
                this.currentInstrument,
                this.currentPeriod,
                indicator.name,
                indicator.params,
                500 // Get more candles for indicator calculation
            );

            console.log(`Indicator ${indicator.name} result:`, result.values?.length || 0, 'values');
            if (this.chart && result.values && result.values.length > 0) {
                this.chart.addIndicator(indicator, result.values);
            }
        } catch (error) {
            console.error(`Failed to calculate indicator ${indicator.name}:`, error.message, error);
            this.showToast(`Failed to load ${indicator.name.toUpperCase()}: ${error.message}`, 'error');
        }
    }

    async reloadAllIndicators() {
        // Called when instrument or period changes
        for (const indicator of this.activeIndicators) {
            await this.calculateAndRenderIndicator(indicator);
        }
    }

    // ==================== Strategy Instance Methods ====================

    async loadStrategyInstances() {
        try {
            this.strategyInstances = await api.getStrategyInstances();
            this.renderStrategyInstances();

            // Also load available strategies for the modal
            this.availableStrategies = await api.getAvailableStrategies();
            this.populateStrategySelect();
        } catch (error) {
            console.error('Failed to load strategy instances:', error);
            this.strategyInstances = [];
            this.renderStrategyInstances();
        }
    }

    populateStrategySelect() {
        const select = document.getElementById('si-strategy');
        if (!select) return;

        // Clear existing options except the first
        select.innerHTML = '<option value="">Select strategy...</option>';

        // Deduplicate strategies by ID
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

    renderStrategyInstances() {
        const container = document.getElementById('strategy-instances-container');
        const countEl = document.getElementById('strategy-instance-count');

        if (countEl) {
            countEl.textContent = this.strategyInstances.length;
        }

        if (!container) return;

        if (this.strategyInstances.length === 0) {
            container.innerHTML = '<div class="empty-state">No saved strategies</div>';
            return;
        }

        container.innerHTML = this.strategyInstances.map(inst => `
            <div class="strategy-instance-item ${inst.enabled ? '' : 'disabled'}" data-id="${inst.id}">
                <div class="si-header">
                    <span class="si-name">${this.escapeHtml(inst.name)}</span>
                    <span class="si-status ${inst.enabled ? 'active' : 'inactive'}">${inst.enabled ? '●' : '○'}</span>
                </div>
                <div class="si-details">
                    <span class="si-strategy">${inst.strategy_id}</span>
                    <span class="si-instrument">${inst.instrument.replace('_', '/')}</span>
                    <span class="si-period">${inst.period}</span>
                </div>
                <div class="si-actions">
                    <button class="si-btn toggle" onclick="app.toggleStrategyInstance('${inst.id}')" title="${inst.enabled ? 'Disable' : 'Enable'}">
                        ${inst.enabled ? '⏸' : '▶'}
                    </button>
                    <button class="si-btn backtest" onclick="app.runStrategyBacktest('${inst.id}')" title="Run Backtest">📊</button>
                    <button class="si-btn edit" onclick="app.editStrategyInstance('${inst.id}')" title="Edit">✏️</button>
                    <button class="si-btn delete" onclick="app.deleteStrategyInstance('${inst.id}')" title="Delete">🗑</button>
                </div>
            </div>
        `).join('');
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    showStrategyInstanceModal(instanceId = null) {
        const modal = document.getElementById('strategy-modal');
        const title = document.getElementById('strategy-modal-title');
        const submitBtn = document.getElementById('si-submit-btn');
        const form = document.getElementById('strategy-instance-form');

        if (!modal || !form) return;

        this.editingInstanceId = instanceId;

        if (instanceId) {
            // Edit mode
            const instance = this.strategyInstances.find(i => i.id === instanceId);
            if (!instance) return;

            title.textContent = 'Edit Strategy Instance';
            submitBtn.textContent = 'Save';

            document.getElementById('si-id').value = instance.id;
            document.getElementById('si-name').value = instance.name;
            document.getElementById('si-strategy').value = instance.strategy_id;
            document.getElementById('si-strategy').disabled = true; // Can't change strategy
            document.getElementById('si-instrument').value = instance.instrument;
            document.getElementById('si-instrument').disabled = true; // Can't change instrument
            document.getElementById('si-period').value = instance.period;
            document.getElementById('si-period').disabled = true; // Can't change period
            document.getElementById('si-params').value = JSON.stringify(instance.parameters, null, 2);
            document.getElementById('si-enabled').checked = instance.enabled;
        } else {
            // Create mode
            title.textContent = 'New Strategy Instance';
            submitBtn.textContent = 'Create';
            form.reset();
            document.getElementById('si-id').value = '';
            document.getElementById('si-strategy').disabled = false;
            document.getElementById('si-instrument').disabled = false;
            document.getElementById('si-period').disabled = false;
            document.getElementById('si-enabled').checked = true;
        }

        modal.classList.remove('hidden');
    }

    hideStrategyInstanceModal() {
        const modal = document.getElementById('strategy-modal');
        if (modal) {
            modal.classList.add('hidden');
        }
        this.editingInstanceId = null;
    }

    async handleStrategyInstanceSubmit(e) {
        e.preventDefault();

        const submitBtn = document.getElementById('si-submit-btn');
        const originalText = submitBtn.textContent;
        submitBtn.disabled = true;
        submitBtn.textContent = 'Saving...';

        try {
            const name = document.getElementById('si-name').value.trim();
            const strategyId = document.getElementById('si-strategy').value;
            const instrument = document.getElementById('si-instrument').value;
            const period = document.getElementById('si-period').value;
            const paramsStr = document.getElementById('si-params').value.trim();
            const enabled = document.getElementById('si-enabled').checked;

            // Parse parameters
            let parameters = {};
            if (paramsStr) {
                try {
                    parameters = JSON.parse(paramsStr);
                } catch (err) {
                    this.showToast('Invalid JSON in parameters', 'error');
                    return;
                }
            }

            if (this.editingInstanceId) {
                // Update existing
                await api.updateStrategyInstance(this.editingInstanceId, {
                    name,
                    parameters,
                    enabled,
                });
                this.showToast('Strategy instance updated', 'success');
            } else {
                // Create new
                await api.createStrategyInstance({
                    name,
                    strategy_id: strategyId,
                    instrument,
                    period,
                    parameters,
                    enabled,
                });
                this.showToast('Strategy instance created', 'success');
            }

            this.hideStrategyInstanceModal();
            await this.loadStrategyInstances();

        } catch (error) {
            this.showToast(error.message || 'Failed to save strategy instance', 'error');
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = originalText;
        }
    }

    editStrategyInstance(instanceId) {
        this.showStrategyInstanceModal(instanceId);
    }

    async toggleStrategyInstance(instanceId) {
        try {
            await api.toggleStrategyInstance(instanceId);
            await this.loadStrategyInstances();
        } catch (error) {
            this.showToast(error.message || 'Failed to toggle strategy instance', 'error');
        }
    }

    async deleteStrategyInstance(instanceId) {
        const instance = this.strategyInstances.find(i => i.id === instanceId);
        if (!instance) return;

        if (!confirm(`Delete "${instance.name}"? This cannot be undone.`)) return;

        try {
            await api.deleteStrategyInstance(instanceId);
            this.showToast('Strategy instance deleted', 'success');
            await this.loadStrategyInstances();
        } catch (error) {
            this.showToast(error.message || 'Failed to delete strategy instance', 'error');
        }
    }

    async runStrategyBacktest(instanceId) {
        const instance = this.strategyInstances.find(i => i.id === instanceId);
        if (!instance) return;

        this.showToast(`Running backtest for "${instance.name}"...`, 'info');

        try {
            const result = await api.runStrategyInstanceBacktest(instanceId, 30);
            const metrics = result.result?.metrics || {};

            // Show summary toast
            const trades = metrics.total_trades || 0;
            const returnPct = parseFloat(metrics.total_return_pct || 0).toFixed(2);
            const winRate = (metrics.win_rate * 100 || 0).toFixed(1);

            this.showToast(
                `Backtest complete: ${trades} trades, ${returnPct}% return, ${winRate}% win rate`,
                trades > 0 ? 'success' : 'info'
            );

            console.log('Backtest result:', result);
        } catch (error) {
            this.showToast(error.message || 'Backtest failed', 'error');
        }
    }

    updateRateDisplay(rate) {
        const priceEl = document.getElementById('chart-price');
        const changeEl = document.getElementById('chart-change');
        const bidEl = document.getElementById('chart-bid');
        const askEl = document.getElementById('chart-ask');
        const spreadEl = document.getElementById('chart-spread');

        // Update main price (mid)
        if (priceEl && rate.mid) {
            priceEl.textContent = rate.mid;
        }

        // Update bid/ask if elements exist
        if (bidEl && rate.bid) {
            bidEl.textContent = rate.bid;
        }
        if (askEl && rate.ask) {
            askEl.textContent = rate.ask;
        }
        if (spreadEl && rate.spread) {
            spreadEl.textContent = rate.spread;
        }

        // Show market status, freshness indicator, or spread info
        if (changeEl) {
            if (rate.tradeable === false) {
                // Market is closed
                changeEl.textContent = 'Market Closed';
                changeEl.className = 'chart-change muted';
            } else if (rate.age_seconds !== undefined && rate.age_seconds > 30) {
                // Market open but data is stale
                changeEl.textContent = `(${rate.age_seconds.toFixed(0)}s stale)`;
                changeEl.className = 'chart-change negative';
            } else if (rate.spread) {
                // Show spread when data is fresh
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
        this.saveSessionState();
        this.loadChartData();

        // Reload indicators for new instrument
        this.reloadAllIndicators();
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
        this.saveSessionState();
        this.loadChartData();

        // Reload indicators for new period
        this.reloadAllIndicators();
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
        const connectionStatus = document.getElementById('connection-status');

        if (connectionStatus) {
            connectionStatus.className = `connection-status ${connected ? 'connected' : ''}`;
            connectionStatus.title = connected ? 'Connected' : 'Disconnected';
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

        // Note: Real-time rates are now handled via WebSocket
        // HTTP polling is only used as fallback (see startHttpPolling)
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

        // Remove after 5 seconds
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
