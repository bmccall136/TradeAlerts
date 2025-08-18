@echo off
cd /d C:\TradeAlerts

:: Guardrails (safe mode: one buy, qty cap = 1)
set GUARDRAILS_ENABLED=true
set LIVE_SAFE_MODE=true
set LIVE_MAX_QTY=1
set BROKER_MODE=ETRADE

:: Optional: lock to a tiny watchlist while testing
:: set WATCHLIST=AAPL,MSFT

:: Launch in a new window; -u = unbuffered output
start "TradeAlerts Live" cmd /k python -u live_start.py
