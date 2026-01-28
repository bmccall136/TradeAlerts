Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = "C:\TradeAlerts"
$Logs = Join-Path $Root "logs"
New-Item -ItemType Directory -Path $Logs -Force | Out-Null
Set-Location $Root

$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$log = Join-Path $Logs ("dashboard_debug_{0}.log" -f $ts)

$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Runner = Join-Path $Root "run_dashboard_noreload.py"

# Kill anything listening on 5000
Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty OwningProcess -Unique |
  ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }

Write-Host "Starting dashboard in FOREGROUND (this window will stay open)..."
Write-Host "Log: $log"
Write-Host ""

# FOREGROUND run so you see the traceback live
& $Python -u $Runner 2>&1 | Tee-Object -FilePath $log

Write-Host ""
Write-Host "Dashboard process exited. See log above."
Read-Host "Press Enter to close"
