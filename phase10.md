# TradingSystem Phase 10 and Beyond

## The Ultimate Goal
The goal of this system is to build an automated trading system that is intelligent and organized and avails itself to leveraging Technical Analysis, Fundamental Analysis, Market Sentiment, Website, Blog and YouTube opinions, and AI assessments, highly focused on statistical analysis. This will, of course, be built in multiple phases.

---

## Phase 10 Implementation Plan

### Architecture Decisions (from planning session)

**Strategy Organization:**
- Strategies remain generic (e.g., `ma_crossover`, `rsi_reversal`)
- StrategyInstance binds a strategy + instrument + period + parameters as a trackable entity
- Filter and compare backtest results by instrument/period
- Indicator roles (signal, confirmation, exit) stay implicit in strategy code for now

**Performance Tracking:**
- Run backtests periodically to detect strategy degradation
- Rolling-window analysis (monthly performance breakdown)
- Live performance tracking once strategy goes live
- All stored efficiently (~20-25MB/year for moderate usage)

**Scale:** Starting with 4-5 currency pairs, 2-3 strategies each (~10-15 instances)

**Indicator Library:** Using existing pandas-ta (150+ indicators). Skip ta-lib, tradingview, github imports for now.

**Claude Indicators:** Natural language → Python generation, iterate and tune, view/backtest from UI. Accessible from both dashboard and Claude Code.

---

### Phase 10.1: UI Indicator Visualization ⬅️ START HERE

**Goal:** Display indicators on charts in the dashboard.

**Scope:**
- Indicator selector in sidebar panel
- Calculate indicator values via existing indicator_service
- Render on TradingView Lightweight Charts:
  - **Overlay indicators** (SMA, EMA, Bollinger Bands) on price pane
  - **Separate pane indicators** (RSI, MACD, ATR) below chart
- Auto-detect display type based on indicator, with user override toggle
- Support up to 10 indicators simultaneously
- Use default parameters initially, allow editing later

**UI Location:** Sidebar panel (new "Indicators" panel)

**Database:** None needed (use existing indicator calculation, render client-side)

**API Endpoints:**
- GET /api/indicators - List available indicators with metadata
- GET /api/indicators/{name} - Get indicator info (params, display type)
- POST /api/charts/{id}/indicators/calculate - Calculate indicator values for chart

---

### Phase 10.2: Saved Strategy Configurations

**Goal:** Persistent StrategyInstance with UI management widget.

**Scope:**
- New `strategy_instances` table:
  ```
  StrategyInstance:
    - id (uuid)
    - name ("GBP Trend Follower")
    - strategy_id ("ma_crossover")
    - instrument ("GBP_USD")
    - period ("D")
    - parameters (JSONB)
    - enabled (bool)
    - created_at
  ```
- API endpoints: create, list, update, delete, run backtest
- Sidebar widget showing saved configurations:
  - Name, strategy, instrument, status
  - Quick actions: Run Backtest, Enable/Disable, Edit, Delete
- Link backtest results to strategy_instance_id

**Database:** New table `strategy_instances`

---

### Phase 10.3: Trade Visualization

**Goal:** Display trades on charts with type-specific markers.

**Scope:**
- Query trades by instrument + time range
- Render on chart:
  - **Live trades:** Up/down arrows (green/red by P&L)
  - **Paper trades:** Up/down triangles
  - **Backtested trades:** Dots
  - **Lines** connecting entry to exit for all types
- Filter by trade type (checkboxes)
- Hover tooltip: entry price, exit price, P&L, strategy

**Database:** Uses existing `positions` table (add `trade_type` column if needed)

---

### Phase 10.4: Claude Indicator Creation

**Goal:** Natural language to Python indicator with UI iteration.

**Scope:**
- Chat interface in dashboard for indicator creation
- Claude generates Python code following BaseIndicator pattern
- Code preview with syntax highlighting
- "Test" button to run on sample data and visualize
- "Save" to persist as custom indicator
- Edit existing indicators through same interface
- Also accessible via Claude Code

**Database:** New `custom_indicators` table

---

### Phase 10.5: Performance Dashboard

**Goal:** Metrics tracking and threshold alerts.

**Scope:**
- Dashboard view showing all strategy instances:
  - Latest backtest metrics (Sharpe, drawdown, win rate)
  - Performance trend (sparkline)
  - Status indicators (green/yellow/red)
- Configurable thresholds per instance:
  - Max drawdown %
  - Min win rate %
  - Min Sharpe ratio
  - Max consecutive losses
- Alert badges when thresholds breached
- Historical performance chart

**Database:** New table `performance_snapshots` or extend `strategy_runs`

---

## Original Planning Notes (preserved for reference)

### Where I need advice:
Here's where I struggle and need options and a recommendation as to how to organize this. If I want to track many Strategies for, as an example, GBP_USD-Oanda-1D, each with potentially several Indicators all acting in different capacities - used for different signals (like signal, confirmation, exit), and backtest them all, and track results over time, what is the best way to set this all up?
We would also want to be able to provide the user an ability to set custom Indicator parameters.

### Indicator Library
- Enable bulk import and leveraging of existing sources
    - Get list of most popular indicators from sources like
        - https://ta-lib.org/wrappers/
        - https://pypi.org/project/tradingview-indicators/
        - Searching Github

### Custom Indicators
- We should also provide the User the ability to create Indicators
    - I would like to use Claude to be able to use plain language to build Indicators
    - I think Indicators should be written in Python

### Viewing Indicators
- Enable Displaying indicators in Chart in UI. Some indicators normally overlay candles, and some do not, and some can be displayed either way.

### Viewing Trades
- We should be able to see Trades on Charts
- Trades should be denoted as real, paper, backtested and what ever else you think
