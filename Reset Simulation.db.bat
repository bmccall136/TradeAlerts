@echo off
REM ── UTF‑8 Console ─────────────────────────────────────────────────────────
chcp 65001 >nul

REM ── Go to script directory ────────────────────────────────────────────────
pushd "%~dp0"

REM ── Delete old simulation DB ─────────────────────────────────────────────
if exist "simulation.db" (
    echo Removing old simulation.db...
    del /q "simulation.db"
) else (
    echo No simulation.db found.
)


REM ── Keep console open ────────────────────────────────────────────────────
echo.
pause

popd
