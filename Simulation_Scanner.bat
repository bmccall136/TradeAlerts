@echo off
REM — Switch console to UTF‑8
chcp 65001 >nul

REM — Force Python into UTF‑8 mode
set PYTHONUTF8=1

REM — Set the window title (with 🚀)
title 🚀 TradeAlerts Runner

REM — Launch PowerShell, cd into this folder, and run your script
powershell -NoExit -ExecutionPolicy Bypass -Command ^
    "cd '%~dp0'; python -X utf8 .\run_simulation.py"
