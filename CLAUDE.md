# TradingSystem - Claude Code Project Instructions

## Commit Workflow

Code and docs are a package — always commit them together. Every commit follows this process:

1. **Stage everything** — code, tests, docs, config changes. Nothing ships separately.
2. **Bump version** in `main.py` to match the tag.
3. **Show current tag** and **ask the user what tag to use** (e.g., "Current tag: v0.45.0. What tag for this commit?").
4. **Write a detailed commit message** — summary line with version and issue reference, then a body listing what changed by category (Database, Backend, Frontend, Tests, Docs).
5. **Tag and push** — tag the commit, push to remote with tags.

Do not commit without asking for the tag. Do not split code and docs into separate commits.

## Development Server

When making changes to frontend files (HTML, CSS, JS) that require testing:
- Claude should restart the server automatically
- User will hard refresh the browser (Cmd+click refresh or Option+Cmd+R in Safari)

### Server Commands

```bash
# Restart server via launchctl (recommended)
launchctl unload ~/Library/LaunchAgents/com.tradingsystem.app.plist
launchctl load ~/Library/LaunchAgents/com.tradingsystem.app.plist

# Or manually with pyenv
source ~/.pyenv/versions/tradingsystem/bin/activate
uvicorn tradingsystem.main:app --port 8002
```

Server runs on **port 8002** (not 8000). Dashboard at http://localhost:8002/ui

## Project Structure

- `src/tradingsystem/` - Python backend (FastAPI)
- `frontend/` - Web dashboard
  - `index.html` - Main page
  - `css/styles.css` - Styles
  - `js/app.js` - Main application logic
  - `js/chart.js` - TradingView chart handling
  - `js/api.js` - API client

## Key Features

- Real-time forex rates via WebSocket streaming
- TradingView Lightweight Charts for price visualization
- OANDA API integration for trading
- Color-coded price movement (green up, red down, blue neutral)

## Dashboard UI

### Header
- Compact 40px height matching instrument tabs
- Account info displayed as pill-style chips (Balance, P&L, Margin)
- Power icon (⏻) connection status: green=connected, red=disconnected
- Toast notifications appear at top-right near power icon

### Sidebar
- "Trading" header with toggle (›/‹) to collapse entire sidebar
- Collapsible panels: Indicators, New Order, Signals, Positions (click header to toggle)
- Panel toggle icon (▼) rotates when collapsed
- Indicators panel: Add up to 10 indicators, select from ~25 common indicators

## Browser Caching

Static CSS/JS files use version query strings for cache-busting.

**When editing frontend files (JS/CSS):**
1. Make the code changes
2. Bump the version in `index.html` (e.g., `?v=0.42.1` → `?v=0.42.2`)
3. Restart the server

This ensures browsers fetch fresh files on normal refresh - no hard refresh needed.

## Phase 10 Development

See `phase10.md` for the full implementation plan. Priority order:
1. **Phase 10.1:** UI Indicator Visualization (sidebar panel, overlay/pane rendering)
2. **Phase 10.2:** Saved Strategy Configurations (StrategyInstance model, UI widget)
3. **Phase 10.3:** Trade Visualization (arrows/triangles/dots on chart)
4. **Phase 10.4:** Claude Indicator Creation (natural language → Python)
5. **Phase 10.5:** Performance Dashboard (metrics, thresholds, alerts)

## Project Documentation

- `TradingSystemAIBuild.md` — master project doc (vision, architecture, current state)
- `phase10.md` — detailed implementation plan for current phase
- Requirement scoping is user-driven. Document what exists; do not propose future features.
