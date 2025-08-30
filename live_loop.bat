@echo off
setlocal
cd /d C:\TradeAlerts

rem --- Mode & guardrails ---
set BROKER_MODE=LIVE
set GUARDRAILS_ENABLED=false

rem --- Safety / sizing (optional) ---
set LIVE_SAFE_MODE=false
set LIVE_MAX_QTY=1
set LIVE_BP_BUFFER=10
set LIVE_TPLUS_DAYS=0
set LIVE_CANDIDATE_LOG_LIMIT=120

rem --- One-run override to ignore buy gate (use only for testing) ---
rem set LIVE_IGNORE_GUARDRAILS_TODAY=1

start "TradeAlerts Live" cmd /k python -u live_start.py
endlocal
