@echo off
cd /d %~dp0
echo 🛑 Stopping scanner...

if not exist scanner.pid (
    echo ❌ No scanner.pid file found.
    exit /b 1
)

set /p PID=<scanner.pid
echo 🔪 Killing scanner process with PID: %PID%
taskkill /PID %PID% /F >nul 2>&1

if %errorlevel% neq 0 (
    echo ❌ Failed to kill process %PID%
) else (
    echo ✅ Scanner process %PID% stopped
    del scanner.pid
)
