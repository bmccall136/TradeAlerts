@echo off
setlocal
cd /d C:\TradeAlerts

REM Resolve PowerShell
set "PSEXE=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%PSEXE%" set "PSEXE=powershell"

REM Allow passing the ps1 path as an argument to this BAT
if not "%~1"=="" (
  set "SCRIPT=%~1"
) else (
  REM Try common names (no need to rename your working file)
  for %%F in ("C:\TradeAlerts\Stop-All*.ps1" "C:\TradeAlerts\Stop All*.ps1" "C:\TradeAlerts\Stop*.ps1") do (
    if exist "%%~fF" (
      set "SCRIPT=%%~fF"
      goto :found
    )
  )
)

:found
if not defined SCRIPT (
  echo Could not find any Stop*.ps1 in C:\TradeAlerts.
  echo Put your working PowerShell script in C:\TradeAlerts (e.g., Stop-All.ps1)
  echo or run:  Stop All (autodiscover).bat "C:\path\to\YourStopAll.ps1"
  pause
  exit /b 2
)

echo Running "%SCRIPT%"
"%PSEXE%" -NoExit -ExecutionPolicy Bypass -File "%SCRIPT%"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo PowerShell returned %RC%
  pause
)
exit /b %RC%
