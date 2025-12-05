@echo off
cd /d C:\TradeAlerts

REM Optional: create a logs folder the first time
if not exist logs mkdir logs

REM Call Python explicitly and log output
"C:\Users\bmccall\AppData\Local\Programs\Python\Python311\python.exe" ^
  "C:\TradeAlerts\update_sp500_symbols.py" ^
  >> "C:\TradeAlerts\logs\update_sp500_symbols.log" 2>&1
