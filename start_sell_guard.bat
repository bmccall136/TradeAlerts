@echo off
setlocal
cd /d C:\TradeAlerts
set "SCRIPT=C:\TradeAlerts\sell_guard.py"
set "LOG=C:\TradeAlerts\logs\sell_guard.log"

REM Kill any previous runs that might hold the log
powershell -NoProfile -ExecutionPolicy Bypass -Command "Stop-Process -Name python -Force -ErrorAction SilentlyContinue; $pat='sell_guard\.py|sell_guard\.log|TradeAlerts|Tee-Object|start_sell_guard'; 'powershell','pwsh','cmd' | ForEach-Object { Get-CimInstance Win32_Process -Filter ('Name=''{0}.exe''' -f $_) -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match $pat } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force } }"

REM If LOG is locked, fall back to a timestamped file
powershell -NoProfile -ExecutionPolicy Bypass -Command "$log='%LOG%'; try { $fs=[IO.File]::Open($log,'Append','Write','None'); $fs.Close() } catch { $ts=Get-Date -Format 'yyyyMMdd-HHmmss'; $log = 'C:\TradeAlerts\logs\sell_guard.' + $ts + '.log'; Write-Host ('[start] Log locked, using ' + $log); [Environment]::SetEnvironmentVariable('SG_LOG',$log,'Process') }"

if defined SG_LOG set "LOG=%SG_LOG%"

set PYTHONUNBUFFERED=1
powershell -NoProfile -ExecutionPolicy Bypass -Command "python -u '%SCRIPT%' 2>&1 | Tee-Object -FilePath '%LOG%' -Append"
endlocal
