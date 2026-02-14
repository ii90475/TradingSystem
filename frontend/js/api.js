/**
 * TradingSystem API Client
 * Wrapper for all backend API calls
 */

const API_BASE = '/api';

class TradingAPI {
    constructor() {
        this.baseUrl = API_BASE;
    }

    async request(endpoint, options = {}) {
        const url = `${this.baseUrl}${endpoint}`;
        const config = {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers,
            },
            ...options,
        };

        try {
            const response = await fetch(url, config);

            if (!response.ok) {
                const error = await response.json().catch(() => ({ detail: response.statusText }));
                throw new Error(error.detail || `HTTP ${response.status}`);
            }

            return await response.json();
        } catch (error) {
            console.error(`API Error [${endpoint}]:`, error);
            throw error;
        }
    }

    // ==================== Live Trading ====================

    async getLiveStatus() {
        return this.request('/live/status');
    }

    async getAccountSummary() {
        return this.request('/live/account');
    }

    async getOpenTrades() {
        return this.request('/live/trades');
    }

    async executeTrade(instrument, side, quantity, stopLoss = null, takeProfit = null) {
        return this.request('/live/trade', {
            method: 'POST',
            body: JSON.stringify({
                instrument,
                side,
                quantity: quantity.toString(),
                stop_loss: stopLoss?.toString(),
                take_profit: takeProfit?.toString(),
            }),
        });
    }

    async closeTrade(positionId) {
        return this.request(`/live/trade/${positionId}/close`, {
            method: 'POST',
        });
    }

    async getRiskStatus() {
        return this.request('/live/risk/status');
    }

    async checkTradeRisk(instrument, side, quantity) {
        return this.request('/live/risk/check', {
            method: 'POST',
            body: JSON.stringify({
                instrument,
                side,
                quantity: quantity.toString(),
            }),
        });
    }

    // ==================== Real-Time Rates ====================

    async getCurrentRate(pair) {
        return this.request(`/rates/current/${pair}`);
    }

    async getCurrentRates(pairs = null) {
        const params = pairs ? `?pairs=${pairs.join('&pairs=')}` : '';
        return this.request(`/rates/current${params}`);
    }

    async getWebSocketStatus() {
        return this.request('/rates/ws/status');
    }

    getWebSocketUrl() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        return `${protocol}//${window.location.host}/api/rates/ws`;
    }

    // ==================== Charts ====================

    async getCharts() {
        return this.request('/charts');
    }

    async getChart(chartId) {
        return this.request(`/charts/${chartId}`);
    }

    async getChartCandles(chartId, start = null, end = null, limit = 100) {
        const params = new URLSearchParams({ limit: limit.toString() });
        if (start) params.append('start', start);
        if (end) params.append('end', end);
        return this.request(`/charts/${chartId}/candles?${params}`);
    }

    async getChartByInstrument(instrument, period) {
        return this.request(`/charts/by-instrument/${instrument}?period=${period}`);
    }

    // ==================== Signals ====================

    async getLatestSignals(strategyId = null, limit = 10) {
        const params = new URLSearchParams({ limit: limit.toString() });
        if (strategyId) params.append('strategy_id', strategyId);
        return this.request(`/signals/latest?${params}`);
    }

    async getSignals(filters = {}) {
        const params = new URLSearchParams();
        Object.entries(filters).forEach(([key, value]) => {
            if (value != null) params.append(key, value.toString());
        });
        return this.request(`/signals?${params}`);
    }

    // ==================== Positions ====================

    async getPositions(status = null) {
        const params = status ? `?status=${status}` : '';
        return this.request(`/positions${params}`);
    }

    async getPosition(positionId) {
        return this.request(`/positions/${positionId}`);
    }

    // ==================== Orders ====================

    async getOrders(status = null, limit = 50) {
        const params = new URLSearchParams({ limit: limit.toString() });
        if (status) params.append('status', status);
        return this.request(`/orders?${params}`);
    }

    // ==================== Strategies ====================

    async getStrategies() {
        return this.request('/strategies');
    }

    async getStrategy(strategyId) {
        return this.request(`/strategies/${strategyId}`);
    }

    // ==================== Dashboard ====================

    async getDashboardSummary() {
        return this.request('/dashboard/summary');
    }

    async getPerformanceMetrics(days = 30) {
        return this.request(`/dashboard/performance?days=${days}`);
    }

    // ==================== Indicators ====================

    async getAvailableIndicators() {
        return this.request('/indicators/available');
    }

    async getIndicatorInfo(name) {
        return this.request(`/indicators/info/${name}`);
    }

    async calculateIndicator(instrument, period, indicatorType, params = {}, limit = 200) {
        const queryParams = new URLSearchParams({
            instrument,
            period,
            indicator_type: indicatorType,
            limit: limit.toString(),
        });
        if (Object.keys(params).length > 0) {
            queryParams.append('params', JSON.stringify(params));
        }
        return this.request(`/indicators/calculate?${queryParams}`, { method: 'POST' });
    }

    // ==================== Session ====================

    async getSession(sessionKey = 'default') {
        return this.request(`/session?session_key=${sessionKey}`);
    }

    async saveSession(sessionData, sessionKey = 'default') {
        return this.request(`/session?session_key=${sessionKey}`, {
            method: 'PUT',
            body: JSON.stringify(sessionData),
        });
    }

    // ==================== Health ====================

    async getHealth() {
        // Health endpoint is at root, not under /api
        const response = await fetch('/health');
        if (!response.ok) throw new Error('Health check failed');
        return response.json();
    }
}

// Export singleton instance
const api = new TradingAPI();
