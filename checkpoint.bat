@echo off
REM checkpoint.bat — stage, commit, and tag a restore point

REM 1) Stage all changes
git add .

REM 2) Commit with your message
git commit -m "🚀 Alerts pipeline live: scanner → API → dashboard"

REM 3) Tag this commit
git tag -a v1.0-alerts-live -m "Alerts pipeline fully functional"

echo.
echo 🎉 Checkpoint created: commit and tag v1.0-alerts-live
pause
