# TradingSystem - Claude Code Project Instructions

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
- Collapsible panels: New Order, Signals, Positions (click header to toggle)
- Panel toggle icon (▼) rotates when collapsed

## Browser Caching

Static CSS/JS files may be cached by the browser. After changes:
1. Restart the server
2. Hard refresh browser (bypasses cache)
