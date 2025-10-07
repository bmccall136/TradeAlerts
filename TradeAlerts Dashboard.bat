@echo off
REM — Switch console to UTF‑8
chcp 65001 >nul

REM — Set the window title (with an emoji)
title 📊 TradeAlerts Dashboard

REM — Launch PowerShell, stay open, cd into this folder, and run the dashboard
powershell -NoExit -ExecutionPolicy Bypass -Command "cd '%~dp0'; python .\dashboard.py"
