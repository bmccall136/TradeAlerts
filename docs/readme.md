# TradeAlerts Pro Suite

> **Built by Ben McCall, powered by Max the AI Sidekick**

---

## 🚀 Overview

TradeAlerts is a next-level, pro-grade stock scanning, simulation, and backtesting platform designed for both rapid signals and in-depth strategy analysis. Featuring a clean black UI, live dashboard, automated simulation, backtest engine, and integrated news failover, it’s built for real traders, by a real trader.

---

## Features

- **Pure black theme** with modern nav bar and responsive layout
- **Alerts Dashboard:** Real-time signal display, Prime filtering, local time, non-repeating cleared alerts
- **Simulation Dashboard:** Tracks holdings, cash, unrealized P&L, and logs every simulated trade
- **Backtest Engine:** Run 1-year strategy backtests, export results, and compare configs
- **Live Config Editing:** Tweak all scanner/backtest variables from the UI
- **Redundant News Feeds:** Multiple API keys auto-rotated, failover for news limits
- **SQLite Backend:** Each major feature (alerts, simulation, backtest) uses its own DB for reliability
- **Engineer-Friendly Controls:** “wr mem” (save), “show run” (status), and easy file structure

---

## File Structure

/TradeAlerts/
dashboard.py
simulation_service.py
backtest_service.py
alert_service.py
config_live.json
config_backtest.json
simulation.db
backtest.db
alerts.db
templates/
alerts.html
simulation.html
backtest.html
static/
style.css
init_alerts_db.sql
init_simulation_db.sql
init_backtest_db.sql
README.md

yaml
Copy
Edit

---

## Quick Start

1. **Install Dependencies**:  
pip install flask pytz

markdown
Copy
Edit

2. **Initialize Databases** (see instructions above)

3. **Run the App**:  
python dashboard.py

yaml
Copy
Edit
Then open `http://localhost:5000` in your browser.

---

## Usage Tips

- Edit live or backtest configs from the Settings page.
- Use “Clear” buttons to dismiss alerts (they won’t return until a *true* new signal appears).
- Backtest engine logs all trade results—downloadable for analysis.
- News quotas are managed automatically; add API keys in the config as needed.

---

## Credits

- **Ben McCall** – Lead developer, system design, and inspiration
- **Max (AI Sidekick)** – Assistant, code generation, documentation, and future-proofing

---

*For questions, tweaks, or new feature requests, just ask Max!*

---
