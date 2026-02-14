/**
 * TradingSystem Chart Module
 * Handles TradingView Lightweight Charts
 */

class ChartManager {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.chart = null;
        this.candlestickSeries = null;
        this.volumeSeries = null;
        this.smaSeries = null;
        this.priceLine = null;
        this.currentInstrument = null;
        this.currentPeriod = 'H1';
        this.lastPrice = null;
        this.previousPrice = null;
        this.priceLineResetTimeout = null;
        this.lastCandleData = null;
        // Store zoom state per instrument+period combination
        this.zoomStateByKey = new Map();
        // Store indicator series by id
        this.indicatorSeries = new Map();
    }

    init() {
        if (!this.container) {
            console.error('Chart container not found');
            return;
        }

        this.chart = LightweightCharts.createChart(this.container, {
            layout: {
                background: { color: '#161b22' },
                textColor: '#8b949e',
            },
            grid: {
                vertLines: { color: '#21262d' },
                horzLines: { color: '#21262d' },
            },
            crosshair: {
                mode: LightweightCharts.CrosshairMode.Normal,
            },
            rightPriceScale: {
                borderColor: '#30363d',
                scaleMargins: {
                    top: 0.1,
                    bottom: 0.2,
                },
            },
            timeScale: {
                borderColor: '#30363d',
                timeVisible: true,
                secondsVisible: false,
            },
        });

        // Add candlestick series with forex price format (5 decimal places)
        this.candlestickSeries = this.chart.addCandlestickSeries({
            upColor: '#3fb950',
            downColor: '#f85149',
            borderDownColor: '#f85149',
            borderUpColor: '#3fb950',
            wickDownColor: '#f85149',
            wickUpColor: '#3fb950',
            priceLineVisible: false,  // Disable default last-value line (we use live WebSocket price)
            lastValueVisible: false,  // Hide last value label on Y-axis
            priceFormat: {
                type: 'price',
                precision: 5,
                minMove: 0.00001,
            },
        });

        // Add volume series
        this.volumeSeries = this.chart.addHistogramSeries({
            priceFormat: { type: 'volume' },
            priceScaleId: '',
        });

        this.volumeSeries.priceScale().applyOptions({
            scaleMargins: {
                top: 0.8,
                bottom: 0,
            },
        });

        // Add SMA series with forex price format (5 decimal places)
        this.smaSeries = this.chart.addLineSeries({
            color: '#58a6ff',
            lineWidth: 2,
            priceLineVisible: false,
            lastValueVisible: false,
            priceFormat: {
                type: 'price',
                precision: 5,
                minMove: 0.00001,
            },
        });

        // Handle resize
        this.resizeObserver = new ResizeObserver(() => {
            if (this.chart && this.container) {
                this.chart.applyOptions({
                    width: this.container.clientWidth,
                    height: this.container.clientHeight,
                });
            }
        });
        this.resizeObserver.observe(this.container);

        // Subscribe to crosshair move for OHLC display (not main price)
        this.chart.subscribeCrosshairMove(this.handleCrosshairMove.bind(this));
    }

    handleCrosshairMove(param) {
        // When cursor leaves chart, show last candle's OHLC
        if (!param.time || !param.seriesData) {
            if (this.lastCandleData) {
                this.updateOHLCDisplay(this.lastCandleData);
            }
            return;
        }

        // When cursor is over chart, show hovered candle's OHLC
        const candleData = param.seriesData.get(this.candlestickSeries);
        if (candleData) {
            this.updateOHLCDisplay(candleData);
        }
    }

    updateOHLCDisplay(data) {
        const openEl = document.getElementById('chart-open');
        const highEl = document.getElementById('chart-high');
        const lowEl = document.getElementById('chart-low');
        const closeEl = document.getElementById('chart-close');

        if (openEl && data.open) openEl.textContent = data.open.toFixed(5);
        if (highEl && data.high) highEl.textContent = data.high.toFixed(5);
        if (lowEl && data.low) lowEl.textContent = data.low.toFixed(5);
        if (closeEl && data.close) closeEl.textContent = data.close.toFixed(5);
    }

    async loadData(instrument, period = 'M5') {
        // Save current zoom state before switching
        this.saveZoomState();

        this.currentInstrument = instrument;
        this.currentPeriod = period;

        // Update time scale format for the new period
        this.updateTimeScaleFormat(period);

        try {
            // Try to get chart data from API
            console.log(`Loading chart for ${instrument} ${period}`);
            const chartData = await api.getChartByInstrument(instrument, period);
            console.log('Chart data:', chartData);

            const candles = await api.getChartCandles(chartData.id, null, null, 200);
            console.log(`Loaded ${candles.length} candles, latest:`, candles[0]);

            this.setData(candles, true);
        } catch (error) {
            console.error('Failed to load chart data:', error);
            // Load mock data as fallback
            this.loadMockData();
        }
    }

    updateTimeScaleFormat(period) {
        if (!this.chart) return;

        // Determine appropriate time format based on period
        const timeScaleOptions = {
            borderColor: '#30363d',
            timeVisible: true,
            secondsVisible: false,
        };

        // Configure tick mark formatter based on period
        if (period.startsWith('M') || period === 'H1') {
            // Minutes or hourly: show time prominently
            timeScaleOptions.tickMarkFormatter = (time, tickMarkType, locale) => {
                const date = new Date(time * 1000);
                if (tickMarkType === LightweightCharts.TickMarkType.Year) {
                    return date.getFullYear().toString();
                }
                if (tickMarkType === LightweightCharts.TickMarkType.Month) {
                    return date.toLocaleDateString(locale, { month: 'short' });
                }
                if (tickMarkType === LightweightCharts.TickMarkType.DayOfMonth) {
                    return date.getDate().toString();
                }
                // For time ticks, show HH:MM
                return date.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit', hour12: false });
            };
        } else if (period === 'H4') {
            // 4-hour: show date and time
            timeScaleOptions.tickMarkFormatter = (time, tickMarkType, locale) => {
                const date = new Date(time * 1000);
                if (tickMarkType === LightweightCharts.TickMarkType.Year) {
                    return date.getFullYear().toString();
                }
                if (tickMarkType === LightweightCharts.TickMarkType.Month) {
                    return date.toLocaleDateString(locale, { month: 'short' });
                }
                if (tickMarkType === LightweightCharts.TickMarkType.DayOfMonth) {
                    return date.toLocaleDateString(locale, { day: 'numeric', month: 'short' });
                }
                return date.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit', hour12: false });
            };
        } else {
            // Daily or longer: show date only
            timeScaleOptions.tickMarkFormatter = (time, tickMarkType, locale) => {
                const date = new Date(time * 1000);
                if (tickMarkType === LightweightCharts.TickMarkType.Year) {
                    return date.getFullYear().toString();
                }
                if (tickMarkType === LightweightCharts.TickMarkType.Month) {
                    return date.toLocaleDateString(locale, { month: 'short', year: 'numeric' });
                }
                return date.toLocaleDateString(locale, { day: 'numeric', month: 'short' });
            };
        }

        this.chart.timeScale().applyOptions(timeScaleOptions);
    }

    /**
     * Get the key for storing zoom state (instrument + period combination).
     */
    getZoomKey() {
        return `${this.currentInstrument}:${this.currentPeriod}`;
    }

    /**
     * Save the current zoom state (visible time range) for the current instrument+period.
     */
    saveZoomState() {
        if (!this.chart || !this.currentInstrument || !this.currentPeriod) return;

        const timeScale = this.chart.timeScale();
        const visibleRange = timeScale.getVisibleRange();

        if (visibleRange) {
            const key = this.getZoomKey();
            this.zoomStateByKey.set(key, {
                from: visibleRange.from,
                to: visibleRange.to,
            });
        }
    }

    /**
     * Restore the saved zoom state for the current instrument+period.
     * Returns true if a saved state was restored, false otherwise.
     */
    restoreZoomState() {
        if (!this.chart || !this.currentInstrument || !this.currentPeriod) return false;

        const key = this.getZoomKey();
        const savedState = this.zoomStateByKey.get(key);

        if (savedState) {
            this.chart.timeScale().setVisibleRange({
                from: savedState.from,
                to: savedState.to,
            });
            return true;
        }

        return false;
    }

    setData(candles, restoreZoom = false) {
        if (!candles || candles.length === 0) {
            this.loadMockData();
            return;
        }

        // Format candle data for TradingView
        const candleData = candles.map(c => ({
            time: this.parseTime(c.time || c.timestamp),
            open: parseFloat(c.open),
            high: parseFloat(c.high),
            low: parseFloat(c.low),
            close: parseFloat(c.close),
        }));

        // Sort by time
        candleData.sort((a, b) => a.time - b.time);

        // Set candlestick data
        this.candlestickSeries.setData(candleData);

        // Set volume data
        const volumeData = candles.map((c, i) => ({
            time: candleData[i].time,
            value: parseFloat(c.volume) || Math.random() * 1000000,
            color: candleData[i].close >= candleData[i].open
                ? 'rgba(63, 185, 80, 0.5)'
                : 'rgba(248, 81, 73, 0.5)',
        }));
        this.volumeSeries.setData(volumeData);

        // Calculate and set SMA
        const smaData = this.calculateSMA(candleData, 20);
        this.smaSeries.setData(smaData);

        // Restore saved zoom state or fit content
        if (restoreZoom && this.restoreZoomState()) {
            // Zoom state restored successfully
        } else {
            this.chart.timeScale().fitContent();
        }

        // Store last candle for OHLC display when cursor is outside chart
        if (candleData.length > 0) {
            this.lastCandleData = candleData[candleData.length - 1];
            this.updateOHLCDisplay(this.lastCandleData);
        }
    }

    parseTime(timeStr) {
        if (typeof timeStr === 'number') return timeStr;

        const date = new Date(timeStr);
        return Math.floor(date.getTime() / 1000);
    }

    calculateSMA(data, period) {
        const sma = [];
        for (let i = period - 1; i < data.length; i++) {
            const sum = data.slice(i - period + 1, i + 1).reduce((acc, d) => acc + d.close, 0);
            sma.push({
                time: data[i].time,
                value: sum / period,
            });
        }
        return sma;
    }

    loadMockData() {
        // Apply time scale format for current period
        this.updateTimeScaleFormat(this.currentPeriod);

        const data = [];
        let time = Math.floor(Date.now() / 1000) - 100 * 3600;
        let open = 1.0800;

        for (let i = 0; i < 100; i++) {
            const volatility = 0.0015;
            const trend = 0.00005;

            const change = (Math.random() - 0.48) * volatility;
            const close = open + change + trend;
            const high = Math.max(open, close) + Math.random() * volatility * 0.5;
            const low = Math.min(open, close) - Math.random() * volatility * 0.5;

            data.push({
                time: time,
                open: parseFloat(open.toFixed(5)),
                high: parseFloat(high.toFixed(5)),
                low: parseFloat(low.toFixed(5)),
                close: parseFloat(close.toFixed(5)),
                volume: Math.floor(Math.random() * 1000000) + 500000,
            });

            open = close;
            time += 3600;
        }

        this.setData(data);
    }

    updateCandle(candle) {
        if (!this.candlestickSeries) return;

        const data = {
            time: this.parseTime(candle.time || candle.timestamp),
            open: parseFloat(candle.open),
            high: parseFloat(candle.high),
            low: parseFloat(candle.low),
            close: parseFloat(candle.close),
        };

        this.candlestickSeries.update(data);
    }

    /**
     * Update the current price line on the chart from real-time rate data.
     * This creates a horizontal price line showing the current bid/ask/mid.
     * Color changes based on price movement:
     * - Green (#3fb950) when price moves up
     * - Red (#f85149) when price moves down
     * - Blue (#58a6ff) when no change for 1 second
     */
    updateCurrentPrice(price) {
        if (!this.candlestickSeries) return;

        const priceValue = parseFloat(price);
        if (isNaN(priceValue)) return;

        // Determine color based on price movement
        let color = '#58a6ff'; // Default blue
        if (this.lastPrice !== null) {
            if (priceValue > this.lastPrice) {
                color = '#3fb950'; // Green - price up
            } else if (priceValue < this.lastPrice) {
                color = '#f85149'; // Red - price down
            }
        }

        this.previousPrice = this.lastPrice;
        this.lastPrice = priceValue;

        // Remove existing price line if any
        if (this.priceLine) {
            this.candlestickSeries.removePriceLine(this.priceLine);
        }

        // Create new price line at current price
        this.priceLine = this.candlestickSeries.createPriceLine({
            price: priceValue,
            color: color,
            lineWidth: 1,
            lineStyle: LightweightCharts.LineStyle.Dashed,
            axisLabelVisible: true,
        });

        // Clear any existing reset timeout
        if (this.priceLineResetTimeout) {
            clearTimeout(this.priceLineResetTimeout);
        }

        // If color changed (not blue), set timeout to revert to blue after 1 second
        if (color !== '#58a6ff') {
            this.priceLineResetTimeout = setTimeout(() => {
                this.resetPriceLineColor();
            }, 1000);
        }
    }

    /**
     * Reset price line to neutral blue color.
     */
    resetPriceLineColor() {
        if (!this.candlestickSeries || this.lastPrice === null) return;

        // Remove existing price line
        if (this.priceLine) {
            this.candlestickSeries.removePriceLine(this.priceLine);
        }

        // Create new price line with blue color
        this.priceLine = this.candlestickSeries.createPriceLine({
            price: this.lastPrice,
            color: '#58a6ff',
            lineWidth: 1,
            lineStyle: LightweightCharts.LineStyle.Dashed,
            axisLabelVisible: true,
        });
    }

    /**
     * Get the current live price.
     */
    getCurrentPrice() {
        return this.lastPrice;
    }

    // ==================== Indicator Methods ====================

    /**
     * Add an indicator to the chart.
     * @param {Object} indicator - Indicator config with id, name, displayType, color, params
     * @param {Array} values - Calculated indicator values
     */
    addIndicator(indicator, values) {
        if (!this.chart || !values || values.length === 0) return;

        console.log(`Adding indicator: ${indicator.name}, displayType: ${indicator.displayType}, values: ${values.length}`);

        // Remove existing series if present (for updates)
        this.removeIndicator(indicator.id);

        // Parse and format the data
        const seriesData = this.formatIndicatorData(values, indicator.name);
        console.log(`Formatted data - mainSeries: ${seriesData.mainSeries.length}, additionalSeries keys:`, Object.keys(seriesData.additionalSeries));

        if (indicator.displayType === 'overlay') {
            // Add as overlay on price pane
            console.log('Adding as OVERLAY on price pane');
            this.addOverlayIndicator(indicator, seriesData);
        } else {
            // Add in separate pane below chart
            console.log('Adding as PANE below chart');
            this.addPaneIndicator(indicator, seriesData);
        }
    }

    /**
     * Format indicator values for TradingView chart.
     * Filters out non-price series for overlay indicators (e.g., BBB%, BBP% from Bollinger Bands).
     */
    formatIndicatorData(values, indicatorName) {
        // Handle different value formats
        const result = {
            mainSeries: [],
            additionalSeries: {},
        };

        // Define which columns to include for known indicators
        // For Bollinger Bands: only include BBL (lower), BBM (middle), BBU (upper)
        // Exclude BBB (bandwidth %) and BBP (percent B) as they're not price values
        const indicatorFilters = {
            'bbands': (key) => key.startsWith('BBL') || key.startsWith('BBM') || key.startsWith('BBU'),
            'kc': (key) => key.startsWith('KCL') || key.startsWith('KCM') || key.startsWith('KCU'),
            'donchian': (key) => key.startsWith('DCL') || key.startsWith('DCM') || key.startsWith('DCU'),
        };

        const filterFn = indicatorFilters[indicatorName.toLowerCase()];

        values.forEach(v => {
            const time = this.parseTime(v.time);

            // Check if this is multi-value (like MACD with macd, signal, histogram)
            let keys = Object.keys(v).filter(k => k !== 'time');

            // Apply filter if one exists for this indicator
            if (filterFn) {
                keys = keys.filter(filterFn);
            }

            if (keys.length === 1 && keys[0] === 'value') {
                // Simple single-value indicator
                if (v.value !== null) {
                    result.mainSeries.push({ time, value: v.value });
                }
            } else if (keys.length > 0) {
                // Multi-value indicator (e.g., MACD, Bollinger Bands)
                keys.forEach(key => {
                    if (v[key] !== null) {
                        if (!result.additionalSeries[key]) {
                            result.additionalSeries[key] = [];
                        }
                        result.additionalSeries[key].push({ time, value: v[key] });
                    }
                });

                // Use first series as main if no explicit 'value'
                if (result.mainSeries.length === 0 && keys.length > 0) {
                    const mainKey = keys[0];
                    result.mainSeries = result.additionalSeries[mainKey] || [];
                    delete result.additionalSeries[mainKey];
                }
            }
        });

        return result;
    }

    /**
     * Add overlay indicator (on price pane).
     */
    addOverlayIndicator(indicator, seriesData) {
        const series = this.chart.addLineSeries({
            color: indicator.color,
            lineWidth: 2,
            priceLineVisible: false,
            lastValueVisible: false,
            priceFormat: {
                type: 'price',
                precision: 5,
                minMove: 0.00001,
            },
        });

        series.setData(seriesData.mainSeries);

        // Store series reference
        this.indicatorSeries.set(indicator.id, {
            type: 'overlay',
            main: series,
            additional: [],
        });

        // Add additional series for multi-value indicators (e.g., Bollinger Bands upper/lower)
        const additionalColors = ['#a371f7', '#f0883e', '#3fb950'];
        let colorIndex = 0;
        for (const [key, data] of Object.entries(seriesData.additionalSeries)) {
            const additionalSeries = this.chart.addLineSeries({
                color: additionalColors[colorIndex % additionalColors.length],
                lineWidth: 1,
                priceLineVisible: false,
                lastValueVisible: false,
                lineStyle: LightweightCharts.LineStyle.Dashed,
                priceFormat: {
                    type: 'price',
                    precision: 5,
                    minMove: 0.00001,
                },
            });
            additionalSeries.setData(data);
            this.indicatorSeries.get(indicator.id).additional.push(additionalSeries);
            colorIndex++;
        }
    }

    /**
     * Add pane indicator (below chart in separate pane).
     */
    addPaneIndicator(indicator, seriesData) {
        // Create a new price scale for this indicator
        const priceScaleId = `indicator-${indicator.id}`;

        const series = this.chart.addLineSeries({
            color: indicator.color,
            lineWidth: 2,
            priceLineVisible: false,
            lastValueVisible: true,
            priceScaleId: priceScaleId,
            priceFormat: {
                type: 'price',
                precision: 2,
                minMove: 0.01,
            },
        });

        // Configure the price scale for the indicator pane
        series.priceScale().applyOptions({
            scaleMargins: {
                top: 0.8,
                bottom: 0.02,
            },
            borderVisible: false,
        });

        series.setData(seriesData.mainSeries);

        // Store series reference
        this.indicatorSeries.set(indicator.id, {
            type: 'pane',
            main: series,
            additional: [],
            priceScaleId: priceScaleId,
        });

        // Add additional series for multi-value indicators (e.g., MACD signal line)
        const additionalColors = ['#f0883e', '#a371f7', '#3fb950'];
        let colorIndex = 0;
        for (const [key, data] of Object.entries(seriesData.additionalSeries)) {
            // Special handling for histogram-type series
            let additionalSeries;
            if (key.toLowerCase().includes('hist')) {
                additionalSeries = this.chart.addHistogramSeries({
                    color: indicator.color,
                    priceLineVisible: false,
                    lastValueVisible: false,
                    priceScaleId: priceScaleId,
                    priceFormat: {
                        type: 'price',
                        precision: 5,
                        minMove: 0.00001,
                    },
                });
                // Color histogram bars based on value
                const histData = data.map(d => ({
                    ...d,
                    color: d.value >= 0 ? 'rgba(63, 185, 80, 0.7)' : 'rgba(248, 81, 73, 0.7)',
                }));
                additionalSeries.setData(histData);
            } else {
                additionalSeries = this.chart.addLineSeries({
                    color: additionalColors[colorIndex % additionalColors.length],
                    lineWidth: 1,
                    priceLineVisible: false,
                    lastValueVisible: false,
                    priceScaleId: priceScaleId,
                    priceFormat: {
                        type: 'price',
                        precision: 2,
                        minMove: 0.01,
                    },
                });
                additionalSeries.setData(data);
            }
            this.indicatorSeries.get(indicator.id).additional.push(additionalSeries);
            colorIndex++;
        }
    }

    /**
     * Remove an indicator from the chart.
     */
    removeIndicator(indicatorId) {
        const seriesInfo = this.indicatorSeries.get(indicatorId);
        if (!seriesInfo) return;

        try {
            // Remove main series
            if (seriesInfo.main) {
                this.chart.removeSeries(seriesInfo.main);
            }
            // Remove additional series
            for (const series of seriesInfo.additional) {
                this.chart.removeSeries(series);
            }
        } catch (error) {
            console.warn('Error removing indicator series:', error);
        }

        this.indicatorSeries.delete(indicatorId);
    }

    /**
     * Set indicator visibility.
     */
    setIndicatorVisible(indicatorId, visible) {
        const seriesInfo = this.indicatorSeries.get(indicatorId);
        if (!seriesInfo) return;

        const options = { visible };

        if (seriesInfo.main) {
            seriesInfo.main.applyOptions(options);
        }
        for (const series of seriesInfo.additional) {
            series.applyOptions(options);
        }
    }

    /**
     * Clear all indicators from the chart.
     */
    clearAllIndicators() {
        for (const indicatorId of this.indicatorSeries.keys()) {
            this.removeIndicator(indicatorId);
        }
    }

    destroy() {
        if (this.priceLineResetTimeout) {
            clearTimeout(this.priceLineResetTimeout);
        }
        if (this.resizeObserver) {
            this.resizeObserver.disconnect();
        }
        if (this.chart) {
            this.chart.remove();
            this.chart = null;
        }
    }
}
