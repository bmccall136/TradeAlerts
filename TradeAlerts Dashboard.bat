@echo off
setlocal
cd /d "%~dp0"

REM Launch the standard PowerShell launcher (venv + crash log)
powershell -ExecutionPolicy Bypass -File "%~dp0Start-Dashboard.ps1"
endlocal
