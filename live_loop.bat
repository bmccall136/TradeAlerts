@echo off
setlocal
cd /d C:\TradeAlerts

REM --- Mode & guardrails (strings: "true"/"false" or "1"/"0") ---
set BROKER_MODE=LIVE
set GUARDRAILS_ENABLED=false
set LIVE_SAFE_MODE=false
set LIVE_MAX_QTY=1

REM --- One-run override to ignore today's gate (optional) ---
set LIVE_IGNORE_GUARDRAILS_TODAY=1

REM Optional: lock to a watchlist IF your app supports WATCHLIST
REM set WATCHLIST=AAPL,MSFT

REM Open a new window and keep it open
start "TradeAlerts Live" cmd /k python -u live_start.py

endlocal
