# Milestone: Automated Trading

Issues to build this milestone, in dependency order.

---

## Data Layer

### Issue 1: Introduce Series entity
Rename existing `charts` table to `series`. Fields: id, instrument, period, created_at. UNIQUE on instrument+period. Update all references (chart_service, API endpoints, frontend). Series is auto-created when a user selects an instrument+period.

### Issue 2: Refactor Chart to reference Series
New `charts` table: id, name, series_id (FK to series), created_at. A Chart is a named view on a Series. Migrate existing chart_indicators FK to point to new charts. Update chart_service, chart model, API endpoints.

### Issue 3: Create chart_strategies table
New table: id, chart_id (FK), strategy_id (str), parameters (JSONB), enabled (bool), created_at, updated_at. Replaces the current strategy_instances table (which duplicates instrument+period instead of referencing a chart). Migrate any existing strategy_instances data.

---

## Strategy Authoring

### Issue 4: Plain English strategy creation (backend)
API endpoint: POST /api/strategies/generate. Accepts a plain English description, calls Claude to generate a BaseStrategy Python subclass. Returns the generated code for review. POST /api/strategies/save accepts reviewed code, writes to strategies directory, registers in StrategyRegistry.

### Issue 5: Strategy validation and testing endpoint
API endpoint: POST /api/strategies/test. Accepts strategy code + instrument + period + date range. Runs the strategy on historical data without saving. Returns signals generated and basic stats. Used for preview before saving.

---

## UI — Chart Management

### Issue 6: Chart creation UI
Add "New Chart" flow to the dashboard. User names the chart, selects instrument+period (or picks an existing Series). Chart appears in a chart selector (tabs or dropdown). Existing indicator panel binds to the active Chart.

### Issue 7: Chart selector / switcher
UI element to switch between named Charts. Shows chart name + series subtitle (e.g., "Euro Scalper" / EUR_USD · H1). Replaces or augments the current instrument tabs + period buttons.

---

## UI — Strategy Assignment

### Issue 8: Strategy assignment panel
In the sidebar, under the Indicators panel, add a "Strategies" section scoped to the active Chart. "+ Add Strategy" opens a picker showing available strategies from the registry. User selects a strategy, configures parameters (defaults pre-filled), and adds it to the Chart. Strategy starts in OFF state.

### Issue 9: Strategy toggle and management
Each strategy assignment on a Chart shows: name, parameters summary, ON/OFF toggle, Edit/Remove/Backtest buttons. Toggle ON/OFF persists to chart_strategies table. Visual indicator of active vs inactive.

### Issue 10: Auto-add required indicators
When a strategy is assigned to a Chart, check its required_indicators against the Chart's current indicators. Auto-add any missing indicators. Warn before removing an indicator that an assigned strategy depends on.

---

## UI — Strategy Authoring

### Issue 11: Plain English strategy creation UI
"Create Strategy" dialog accessible from the strategy picker. Text input for plain English description. Shows generated Python code for review. "Iterate" button to refine with follow-up instructions. "Save" persists and registers the strategy. Saved strategies appear in the strategy library.

---

## Trading Mode

### Issue 12: Paper/Live trading toggle and dual API keys
Add `oanda_paper_api_key`, `oanda_paper_account_id`, and `oanda_paper_api_url` to config and `.env`. UI toggle in the header or sidebar to switch between Paper and Live modes. Paper mode uses OANDA practice API (`https://api-fxpractice.oanda.com`) with the paper API key. Live mode uses the production API with the live key. Visual indicator of current mode — prominent and unmistakable (e.g., colored banner: green=paper, red=live). Mode selection gates which API key the OANDA trading client uses at runtime. Default to Paper. Require explicit confirmation to switch to Live.

---

## Execution Engine

### Issue 13: Bar close detection service
Background service that monitors Series for completed candles. Polls RateService on a schedule matching each Series' period. Detects when a new candle appears (previous bar closed). Emits bar-close events per Series.

### Issue 14: Strategy execution on bar close
On bar-close event: find all Charts on the Series, find all enabled strategy assignments, compute indicators, call generate_signals(). Log all signals to signals table.

### Issue 15: Signal-to-order pipeline
Convert BUY/SELL signals into orders via OANDA trading client. Route through paper or live API based on current trading mode (Issue 12). Apply risk controls (position sizing, daily loss limit, max positions). Log orders to orders table with trading mode recorded.

---

## Dependency Order

```
                    ┌─── Issue 4  (plain English backend)
                    │      └── Issue 5  (strategy testing)
                    │            └── Issue 11 (plain English UI)
                    │
Issue 1  (Series)   │
  └── Issue 2  (Chart refactor)
        ├── Issue 3  (chart_strategies table)
        │     ├── Issue 8  (strategy assignment panel)
        │     │     └── Issue 10 (auto-add indicators)
        │     └── Issue 9  (strategy toggle UI)
        ├── Issue 6  (chart creation UI)
        │     └── Issue 7  (chart switcher)
        ├── Issue 12 (paper/live toggle)
        └── Issue 13 (bar close detection)
              └── Issue 14 (strategy execution)
                    └── Issue 15 (signal-to-order — depends on 12 + 14)
```

Issues 4→5→11 (plain English authoring) are independent and can be built in parallel with everything else.
