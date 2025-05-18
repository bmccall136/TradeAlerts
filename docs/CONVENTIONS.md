# Project Conventions

## Routes
- `alerts_index` → GET `/alerts`
- `clear_alerts` → POST `/alerts/clear`
- `simulation_index` → GET `/simulation`
- `buy_route` → POST `/simulation/buy`
- `sell_route` → POST `/simulation/sell`

## Templates
- `templates/alerts.html`
- `templates/simulation.html`

## Context Variables
- `alerts`: list of dicts `{ id, symbol, price, status, confidence, timestamp, spark, triggers }`
- `current_filter`
- `news_api_key`

## DB Path
In `services/alert_service.py`:
```python
import os
DB = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'alerts.db'))

ETRADE_API_KEY=1e0978925ddea6a6addb5436e6ff2164
ETRADE_API_SECRET=0fdac4a22a68112d7e855281bab9df70af85cfd023206d15d75bcf51f1390bc2
OAUTH_TOKEN=Vke2hWOaff2rr+cWbh2V9okjFp5wADsimK4q/lKHheU=
OAUTH_TOKEN_SECRET=rHE0AgP+3V+PQHZtzTnBnVo80H70GXKn4TzckeYQuNc=
ETRADE_ENV=production

CONSUMER_KEY=1e0978925ddea6a6addb5436e6ff2164
CONSUMER_SECRET=0fdac4a22a68112d7e855281bab9df70af85cfd023206d15d75bcf51f1390bc2

NEWSAPI_KEY=12f1f678b30a4a5d929ebf218d515ca3

# Restore baseline:
git reset --hard HEAD
git clean -fd

# Copy in final files:
Copy-Item .\dashboard-final.py .\dashboard.py -Force
Copy-Item .\alerts-final.html .\templates\alerts.html -Force
Copy-Item .\alert_service-final.py .\services\alert_service.py -Force
Copy-Item .\style-final.css .\static\style.css -Force
Copy-Item .\simulation-final.html .\templates\simulation.html -Force

# Restart:
python .\dashboard.py
