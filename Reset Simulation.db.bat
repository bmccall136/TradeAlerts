@echo off
REM — Switch console to UTF‑8
chcp 65001 >nul


REM — Launch PowerShell, stay open, cd into this folder, and run the dashboard
powershell -NoExit -ExecutionPolicy Bypass -Command "cd '%~dp0'; del simulation.db; python .\init_simulation_db.py"
