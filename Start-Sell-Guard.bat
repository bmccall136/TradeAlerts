@echo off
setlocal enableextensions
cd /d C:\TradeAlerts
powershell -NoExit -ExecutionPolicy Bypass -File "C:\TradeAlerts\Start-Sell-Guard (keep-open PID).ps1"
