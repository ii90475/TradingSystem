# Automated Trading System — Design Document

## Nomenclature

| Term | Definition | Example |
|------|-----------|---------|
| **Instrument** | A tradable pair | `EUR_USD` |
| **Series** | Instrument + Period — the OHLCV data stream | `EUR_USD · H1` |
| **Chart** | Named view = Series + Indicators. The analytical workspace. | "Euro Scalper" = EUR_USD · H1 + EMA(10), EMA(20) |
| **Strategy** | A Python class that generates BUY/SELL signals from indicator conditions | `ma_crossover`, `rsi_reversal` |
| **Strategy Assignment** | A Strategy bound to a Chart with parameters and an on/off toggle | ma_crossover on "Euro Scalper" with {fast: 10, slow: 20} [ON] |
| **Indicator** | A formulaic calculation on OHLCV candle data | EMA(20), RSI(14), Bollinger Bands(20, 2) |

### Hierarchy

```
Instrument: EUR_USD
  └── Series: EUR_USD · H1                    ← raw data stream (auto-created)
        ├── Chart: "Euro Scalper"             ← named view (user-created)
        │     ├── Indicators: EMA(10), EMA(20)
        │     ├── Strategy: ma_crossover [ON]
        │     └── Strategy: rsi_reversal [OFF]
        └── Chart: "Euro Mean Revert"
              ├── Indicators: RSI(14), BBands(20,2)
              └── Strategy: bollinger_breakout [ON]
```

- A **Series** is the data. It exists whether anyone is looking at it.
- A **Chart** is the lens. Multiple Charts can share the same Series.
- A **Strategy** is the actor. It reads a Chart's indicators and generates signals.
- Multiple Strategies can be assigned to one Chart. Each is independently toggleable.

---

## How It Works

### Data Flow

```
OANDA → RateService → Series (OHLCV candles)
                          ↓
                       Chart (applies Indicators)
                          ↓
                    Strategy (evaluates conditions)
                          ↓
                    Signal → Order → OANDA
```

### Execution Engine

On each bar close for a given Series:
1. Find all Charts on that Series
2. For each Chart, find all enabled Strategy Assignments
3. Compute the Chart's indicators on the latest candles
4. Call each Strategy's `generate_signals()` with the candle + indicator data
5. Convert BUY/SELL signals into orders via OANDA trading client
6. Apply risk limits (max position size, max daily loss, max open positions)

### Bar Close Detection

The execution engine monitors RateService for completed candles. When a new candle appears for a Series, the previous bar is "closed" and strategies evaluate.

---

## Strategy Creation

### Option 1: Python (Direct)

Subclass `BaseStrategy` and implement `generate_signals()`:

```python
class MyStrategy(BaseStrategy):
    name = "My Strategy"
    description = "Buy when RSI exits oversold"
    required_indicators = [
        IndicatorConfig("rsi", {"length": 14}),
    ]
    default_params = {"oversold": 30}

    def generate_signals(self, context: StrategyContext) -> list[Signal]:
        rsi = context.indicators["rsi"]
        if rsi.iloc[-2] < self.params["oversold"] < rsi.iloc[-1]:
            return [self.create_signal(SignalType.BUY, context.instrument,
                                        strength=0.8, reason="RSI exits oversold")]
        return []
```

Place the file in `src/tradingsystem/strategies/examples/` and it auto-registers.

### Option 2: Plain English (Claude-Generated)

Describe a strategy in natural language. Claude generates the Python `BaseStrategy` subclass. The user can review, test, and iterate.

Example input:
> "Buy when the 10-period EMA crosses above the 50-period EMA and RSI is below 60. Sell when the 10 EMA crosses below the 50 EMA."

Claude produces a complete Python file following the BaseStrategy pattern. The generated code is the same as hand-written — no runtime interpretation, no DSL, just Python.

Both options produce the same artifact: a Python file in the strategies directory.

---

## UI Workflows

### Creating a Chart

1. User selects Instrument and Period (Series is auto-created if needed)
2. User clicks "New Chart" → enters a name (e.g., "Euro Scalper")
3. Chart is created, linked to the Series
4. User adds Indicators from the sidebar panel

### Assigning a Strategy to a Chart

1. User opens a Chart
2. In the Strategies sidebar panel, clicks "+ Add Strategy"
3. Selects from strategy library (ma_crossover, rsi_reversal, etc.)
4. Configures parameters (defaults pre-filled, editable)
5. Strategy's required indicators are auto-added to the Chart if not already present
6. Strategy is added in OFF state
7. User toggles ON when ready

### Toggling Strategies

Each Strategy Assignment on a Chart shows:
- Strategy name and parameters
- ON/OFF toggle
- Edit (parameters), Remove, Backtest buttons

Toggling ON means the execution engine will evaluate this strategy on each bar close. Toggling OFF pauses it without removing the configuration.

### Creating a Strategy via Plain English

1. User opens a "Create Strategy" dialog
2. Types a plain English description of entry/exit conditions
3. Claude generates the Python strategy code
4. User previews the code and can iterate ("make it also check volume > average")
5. User clicks "Save" — strategy is saved as a Python file and registered
6. Strategy appears in the library for assignment to any Chart

---

## Persistence

| Entity | Storage | Identity |
|--------|---------|----------|
| Series | `series` table (PostgreSQL) | instrument + period (UNIQUE) |
| Chart | `charts` table | UUID, name, series_id (FK) |
| Chart Indicators | `chart_indicators` table | chart_id (FK), indicator_type, parameters (JSONB) |
| Strategy (code) | Python files on disk | strategy_id (filename/class name) |
| Strategy Assignment | `chart_strategies` table | chart_id (FK), strategy_id, parameters (JSONB), enabled (bool) |
| Signals | `signals` table | Generated by strategies, timestamped |
| Orders | `orders` table | Created from signals |
| Positions | `positions` table | Tracks open/closed trades |

---

## Built-in Strategies

| Strategy | Type | Entry Logic | Key Parameters |
|----------|------|------------|----------------|
| MA Crossover | Trend | Fast EMA crosses slow EMA | fast_period: 10, slow_period: 20 |
| RSI Reversal | Mean-reversion | RSI exits oversold/overbought | rsi_period: 14, oversold: 30, overbought: 70 |
| Bollinger Breakout | Volatility | Price re-enters Bollinger Bands | bb_period: 20, bb_std: 2.0 |
| MACD Divergence | Momentum | Price/MACD divergence | macd_fast: 12, macd_slow: 26, macd_signal: 9 |
| ATR Trailing | Trend + stops | EMA crossover + ATR trailing stop | ema_fast: 10, atr_period: 14, atr_multiplier: 2.0 |
| Ichimoku Cloud | Trend | Price vs cloud + Tenkan/Kijun cross | tenkan: 9, kijun: 26, senkou_b: 52 |
| Multi-Timeframe | Trend alignment | HTF trend + LTF EMA crossover | entry_ema_fast: 10, trend_ema: 50, htf_multiplier: 4 |
| Support/Resistance | Price action | S/R level breakouts | lookback: 50, min_touches: 2, breakout_pct: 0.001 |

---

## Trading Modes: Paper vs Live

The system supports two trading modes, each with its own OANDA API credentials:

| | Paper | Live |
|---|-------|------|
| **API URL** | `https://api-fxpractice.oanda.com` | `https://api-fxtrade.oanda.com` |
| **API Key** | `OANDA_PAPER_API_KEY` | `OANDA_API_KEY` |
| **Account ID** | `OANDA_PAPER_ACCOUNT_ID` | `OANDA_ACCOUNT_ID` |
| **Default** | Yes | No |

- The UI displays current mode prominently — green banner for Paper, red for Live
- Switching to Live requires explicit confirmation
- All orders record which mode they were placed in
- The execution engine routes signals through whichever API the current mode dictates
- Paper and Live use real OANDA APIs (practice vs production) — not simulated

---

## Risk Controls

Configured in `config.py`:
- `max_position_size_pct`: 5% of account per position
- `max_daily_loss_pct`: 2% max daily drawdown
- `max_open_positions`: 5 concurrent positions
- Trading mode toggle (Paper/Live) determines which OANDA API receives orders
