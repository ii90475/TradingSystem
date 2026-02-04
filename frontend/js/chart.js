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
        this.currentInstrument = null;
        this.currentPeriod = 'H1';
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

        // Add candlestick series with forex price format (4 decimal places)
        this.candlestickSeries = this.chart.addCandlestickSeries({
            upColor: '#3fb950',
            downColor: '#f85149',
            borderDownColor: '#f85149',
            borderUpColor: '#3fb950',
            wickDownColor: '#f85149',
            wickUpColor: '#3fb950',
            priceFormat: {
                type: 'price',
                precision: 4,
                minMove: 0.0001,
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

        // Add SMA series with forex price format
        this.smaSeries = this.chart.addLineSeries({
            color: '#58a6ff',
            lineWidth: 2,
            priceLineVisible: false,
            lastValueVisible: false,
            priceFormat: {
                type: 'price',
                precision: 4,
                minMove: 0.0001,
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

        // Subscribe to crosshair move for price display
        this.chart.subscribeCrosshairMove(this.handleCrosshairMove.bind(this));
    }

    handleCrosshairMove(param) {
        if (!param.time || !param.seriesData) return;

        const candleData = param.seriesData.get(this.candlestickSeries);
        if (candleData) {
            this.updatePriceDisplay(candleData);
        }
    }

    updatePriceDisplay(data) {
        const priceEl = document.getElementById('chart-price');
        const openEl = document.getElementById('chart-open');
        const highEl = document.getElementById('chart-high');
        const lowEl = document.getElementById('chart-low');
        const closeEl = document.getElementById('chart-close');
        const changeEl = document.getElementById('chart-change');

        if (priceEl && data.close) {
            priceEl.textContent = data.close.toFixed(5);
        }

        // Update OHLC values
        if (openEl && data.open) openEl.textContent = data.open.toFixed(5);
        if (highEl && data.high) highEl.textContent = data.high.toFixed(5);
        if (lowEl && data.low) lowEl.textContent = data.low.toFixed(5);
        if (closeEl && data.close) closeEl.textContent = data.close.toFixed(5);

        if (changeEl && data.open && data.close) {
            const change = data.close - data.open;
            const changePct = (change / data.open) * 100;
            const sign = change >= 0 ? '+' : '';
            changeEl.textContent = `${sign}${change.toFixed(5)} (${sign}${changePct.toFixed(2)}%)`;
            changeEl.className = `chart-change ${change >= 0 ? 'positive' : 'negative'}`;
        }
    }

    async loadData(instrument, period = 'M5') {
        this.currentInstrument = instrument;
        this.currentPeriod = period;

        try {
            // Try to get chart data from API
            console.log(`Loading chart for ${instrument} ${period}`);
            const chartData = await api.getChartByInstrument(instrument, period);
            console.log('Chart data:', chartData);

            const candles = await api.getChartCandles(chartData.id, null, null, 200);
            console.log(`Loaded ${candles.length} candles, latest:`, candles[0]);

            this.setData(candles);
        } catch (error) {
            console.error('Failed to load chart data:', error);
            // Load mock data as fallback
            this.loadMockData();
        }
    }

    setData(candles) {
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

        // Fit content
        this.chart.timeScale().fitContent();

        // Update price display with last candle
        if (candleData.length > 0) {
            const lastCandle = candleData[candleData.length - 1];
            this.updatePriceDisplay(lastCandle);
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
        this.updatePriceDisplay(data);
    }

    destroy() {
        if (this.resizeObserver) {
            this.resizeObserver.disconnect();
        }
        if (this.chart) {
            this.chart.remove();
            this.chart = null;
        }
    }
}
