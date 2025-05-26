# Project Conventions

## Routes
- `alerts_index` → GET `/alerts`
- `clear_alerts` → POST `/alerts/clear`
- `simulation_index` → GET `/simulation`
- `buy_route` → POST `/simulation/buy`
- `sell_route` → POST `/simulation/sell`
- `backtest_index` → GET `/backtest`
- `promote_settings` → POST `/api/promote_settings`

## Templates
- `templates/alerts.html`
- `templates/simulation.html`
- `templates/backtest.html`

## Context Variables
- `alerts`: list of dicts `{ id, symbol, price, status, confidence, timestamp, spark, triggers }`
- `backtest_results`: list of dicts `{ symbol, buy_time, buy_price, sell_time, sell_price, pl, exit_reason }`
- `current_filter`
- `strategy_params`: dict of tweakable strategy parameters (profit_target, stop_loss, hold_time, min_triggers, etc.)
- `news_api_key`

## Config Handling
- UI-based parameter controls are available in `/backtest` and (optionally) on the live dashboard.
- Strategy parameters are saved to `config.json` and shared between backtest and live scanner.
- The "Promote to Live" button in the backtest page updates the shared config, instantly applying those parameters to the live scanner.

## DB Path
In `services/alert_service.py`:
```python
import os
DB = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'alerts.db'))
```
- **Backtest results** are *not* stored in the database by default; export as CSV if needed.

## Navigation
- All pages feature a nav bar with shortcuts to Trade Alerts, Simulation, Backtest, and Settings (if present).
