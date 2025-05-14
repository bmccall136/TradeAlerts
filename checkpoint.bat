@echo off
REM checkpoint.bat — stage, commit, and tag a restore point

REM 1) Stage all changes
git add .

REM 2) Commit with your message
git commit -m "🚀 Alerts pipeline live: scanner → API → dashboard"

REM 3) Delete existing tag if it exists to avoid errors
git tag -l v1.0-alerts-live >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Tag v1.0-alerts-live exists, deleting old tag...
    git tag -d v1.0-alerts-live
)

REM 4) Create annotated tag
git tag -a v1.0-alerts-live -m "Alerts pipeline fully functional"

echo.
echo 🎉 Checkpoint created: commit and tag v1.0-alerts-live
pause
