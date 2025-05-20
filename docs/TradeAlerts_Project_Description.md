# TradeAlerts Project Description

## Overview
TradeAlerts is a Flask-based web application that provides real-time trade alerts based on technical indicators. It includes both a **dashboard** for visualizing incoming alerts in a table with filters, sparklines, and action buttons, and a **scanner** script that fetches market data, computes indicator‐based signals, scores confidence, and posts alerts to the API.

## Components

- **dashboard.py**  
  - Main Flask application entrypoint.  
  - Registers the **API blueprint** (`/api/alerts`, `/api/status`).  
  - Defines the **Sparkline SVG endpoint** (`/sparkline/<id>.svg`) to render inline sparklines.  
  - Renders `templates/alerts.html` with current filters (`All`, `Prime`, `Sell`) and alert data.

- **api.py**  
  - Flask blueprint exposing:
    - `GET /api/alerts`: list alerts as JSON  
    - `POST /api/alerts`: ingest new alerts from the scanner  
    - `GET /api/status`: market connectivity status  

- **templates/alerts.html**  
  - Jinja2 template for the dashboard UI.  
  - Presents columns: Symbol, Name, Signal (with emojis), Confidence, Price, Timestamp, Sparkline, Triggers (with clickable news‑article links when available), VWAP, Action.  
  - Filters: **All**, **Prime**, **Sell** (current filter displayed in the page title).

- **static/js/script.js**  
  - Client‐side JavaScript that:
    - Fetches alert data from `/api/alerts`.  
    - Renders the table dynamically.  
    - Handles filter navigation and polling.  
    - Embeds `<img src="/sparkline/{{id}}.svg">` for sparklines.

- **services/alert_service.py**  
  - Database access layer (SQLite).  
  - Functions: `insert_alert(data)`, `get_alerts(filter)`, `clear_filtered(filter)` (formerly `clear_alerts`).  
  - Stores alerts with fields: id, symbol, name, signal, confidence, price, timestamp, sparkline (CSV string), triggers (list of strings or hyperlinks), vwap, buy_sell.

- **services/news_service.py**  
  - Fetches headlines from NewsAPI only for **Prime** alerts.  
  - Computes simple sentiment and retains the top article’s URL for clickable trigger badges.

- **services/market_service.py**  
  - Orchestrates data pulls and indicator logic:  
    - Fetches live quotes from E*TRADE (production only, controlled by `ETRADE_ENV=production`).  
    - Fetches OHLC bars via yfinance.  
    - Builds triggers (TREND, RSI, MACD, VWAP, VOLUME, ATR).  
    - Assigns **Prime** alerts (≥ 3 triggers including a positive news signal) with 100% confidence; all others are ignored (no “Sharpshooter” tier).

- **scanner.py** (production)  
  - Loops continuously through the S&P 500 list.  
  - Calls the market service, then posts each **Prime** alert to the API.

- **scanner_test.py** (test mode)  
  - Mirrors `scanner.py` logic but runs once through all tickers, sleeping between symbols for offline testing.

- **alerts_clean.db**  
  - SQLite database storing alert records.

## Installation & Setup

1. **Clone the repo**  
2. **Create a virtual environment** and install dependencies:  
   ```bash
   pip install flask yfinance pandas python-dotenv requests newsapi-python oauthlib requests-oauthlib
3. Configure .env at project root with:

dotenv
Copy
Edit
API_URL=http://localhost:5000/api/alerts
SYMBOLS_FILE=sp500.txt
SCAN_INTERVAL=300
ETRADE_ENV=production
ETRADE_API_KEY=…
ETRADE_API_SECRET=…
OAUTH_TOKEN=…
OAUTH_TOKEN_SECRET=…
NEWSAPI_KEY=…
4. Initialize database if needed (the alerts_clean.db).

5. Run the dashboard:

bash
Copy
Edit
python dashboard.py
6. Launch the scanner:

bash
Copy
Edit
python scanner.py
Git Recovery Point
bash
Copy
Edit
# Stage all changes
git add .

# Commit with a descriptive message
git commit -m "chore: update project description to reflect Prime/Sell only, news links"

# (Optional) Tag this release
git tag -a v1.1.0 -m "Prime alerts & news‑link support"

# Push commits and tags
git push origin main --tags