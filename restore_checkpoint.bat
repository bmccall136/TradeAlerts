@echo off
REM restore_checkpoint.bat — reset to alerts‑live tag

REM 1) Fetch any missing tags
git fetch --tags

REM 2) Reset current branch to the tag (destructive!)
git reset --hard v1.0-alerts-live

echo.
echo ✅ Restored working tree to v2.0-alerts-live
pause
