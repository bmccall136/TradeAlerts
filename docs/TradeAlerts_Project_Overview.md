TradeAlerts Project Overview
🚀 TradeAlerts Project: High‑Level Architecture

1. Purpose & Workflow
   - Signal Scanner: Runs continuously (every 60 s) over your S&P 500 universe, fetching raw price quotes via the E*TRADE API and intraday statistics (RSI, MACD, Bollinger Bands, VWAP, volume) via Yahoo Finance. It applies your configured thresholds to identify Buy and Sell signals.
   - Alert Delivery: When a signal meets your confidence criteria, the scanner pings the Dashboard backend via a POST to /api/alerts. Alerts are recorded in your local alerts_clean.db SQLite table, then surfaced in the Trade Alerts page.
   - Dashboard UI: A Flask app with four blueprints:
     1. API Blueprint (/api): receives and exposes alerts JSON.
     2. Alerts Blueprint (/alerts): renders the alerts table with SVG sparklines and Clear All.
     3. Simulation Blueprint (/simulation): allows simulating buys at alert time, tracking cash/positions/trade history in simulation.db, and resetting the simulation.
     4. Status Blueprint (/status): shows live connectivity indicators for Yahoo Finance Intraday and E*TRADE API with a one-click Reconnect API link.
   - Styling & Layout: A single base.html using Bootstrap’s container-fluid and a dark‑mode theme. All pages extend base.html for consistent headers, typography, and responsive behavior. The Alerts page spans the full window, with centered title and filters, right-aligned status badges, and a horizontally scrollable, no-wrap table with SVG sparklines. The Simulation page mirrors this dark‑theme aesthetic, with a Reset button, real‑time cash/open value/realized P&L stats, and tables for open positions and trade history.

🗂 Project Structure

TradeAlerts/
├── dashboard.py
├── alerts_clean.db
├── simulation.db
├── templates/
│   ├── base.html
│   ├── alerts.html
│   └── simulation/index.html
├── static/
│   └── style.css
├── blueprints/
│   ├── api/views.py
│   ├── alerts/views.py
│   ├── simulation/views.py
│   └── status/views.py
└── services/
    ├── alert_service.py
    ├── simulation_service.py
    └── status_service.py

🔧 Key Components & Recent Enhancements
Component	Role	Recent Tweaks
Scanner (scanner.py)	Fetches raw price from E*TRADE API and computes intraday indicators via Yahoo Finance → POST /api/alerts	Unified MACD/RSI/VWAP/Volume logic, fixed formatting
alert_service.py	CRUD for alerts + sparkline SVG generator	Inline SVG sparklines, trigger parsing, clean filtering
alerts.html	Main Trade Alerts page	Bootstrap table, full-width layout, centered filters, stacked status badges
simulation_service.py	Manages cash, positions, trade history	Buy/reset endpoints with stub logic
simulation/index.html	Simulation Dashboard	Dark-mode tables for positions and history
status_service.py	Checks connectivity to Yahoo & E*TRADE	Live status badges, reconnect link
🎉 Where We Stand

– All core flows (price fetch, indicator calc, alert ingestion, display, filtering, simulation) are wired end-to-end.
– UI consistency via base.html + Bootstrap.
– Interactive features (filters, clear, simulation buy/reset) operational.
– SVG sparklines provide quick trend views.

Next steps may include:
- Historical backtesting
- Notification hooks (email, Slack)
- Expanded indicator set (ATR, stochastic, AI-driven)
- Responsive refinements (mobile interactivity)
