@echo off
REM Launch Dashboard first and give it time to bind port
cd /d "%~dp0"

REM Start Dashboard (keep window open)
start "Dashboard" cmd /k python dashboard.py

REM Wait 5 seconds for dashboard to initialize
timeout /t 5 /nobreak

REM Start Scanner (keep window open)
start "Scanner" cmd /k python scanner.py

REM Exit launcher
exit
