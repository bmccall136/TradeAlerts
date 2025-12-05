# C:\TradeAlerts\update_sp500_task.ps1

$ErrorActionPreference = 'Stop'

# 1) Work from the TradeAlerts folder
Set-Location 'C:\TradeAlerts'

# 2) Ensure logs folder exists
$logDir = Join-Path (Get-Location) 'logs'
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}

# 3) Define paths
$python = 'C:\Users\bmccall\AppData\Local\Programs\Python\Python311\python.exe'
$script = 'C:\TradeAlerts\update_sp500_symbols.py'
$log    = Join-Path $logDir 'update_sp500_symbols.log'

# 4) Mark the run in the log
"==== Run at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ====" | Out-File -FilePath $log -Append

# 5) Actually run Python and append all output/errors to the log
try {
    & $python $script *>> $log 2>&1
}
catch {
    "ERROR: $($_.Exception.Message)" | Out-File -FilePath $log -Append
    exit 1
}
