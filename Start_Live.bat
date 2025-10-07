@echo off
setlocal enableextensions
cd /d C:\TradeAlerts

REM Visible PowerShell window, keep open (-NoExit), run script
if exist "C:\TradeAlerts\Start-Live.ps1" (
  powershell -NoExit -ExecutionPolicy Bypass -File "C:\TradeAlerts\Start-Live.ps1"
) else (
  echo Missing C:\TradeAlerts\Start-Live.ps1
  pause
)
