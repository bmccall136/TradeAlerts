@echo off
cd /d C:\TradeAlerts
echo Running with visible console for diagnostics...
echo.
powershell -NoExit -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Continue'; cd 'C:\TradeAlerts'; & 'C:\Users\bmccall\AppData\Local\Programs\Python\Python311\python.exe' '.\etrade_auth_flow.py'"
