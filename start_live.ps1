# C:\TradeAlerts\start_live.ps1
$ErrorActionPreference = 'Stop'
Set-Location 'C:\TradeAlerts'
$host.UI.RawUI.WindowTitle = 'TradeAlerts Live'

# Make Unicode output safe
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding           = [System.Text.UTF8Encoding]::new()

# --- Mode & guardrails ---
$env:BROKER_MODE        = 'LIVE'
$env:GUARDRAILS_ENABLED = 'false'

# --- Safety / sizing (optional) ---
$env:LIVE_SAFE_MODE         = 'false'
$env:LIVE_MAX_QTY           = '1'
$env:LIVE_BP_BUFFER         = '10'
$env:LIVE_TPLUS_DAYS        = '0'
$env:LIVE_CANDIDATE_LOG_LIMIT = '120'
# Testing override only:
# $env:LIVE_IGNORE_GUARDRAILS_TODAY = '1'

# Log file
if (-not (Test-Path .\logs)) { New-Item -ItemType Directory -Path .\logs | Out-Null }
$log = Join-Path $PWD ("logs\live_{0}.log" -f (Get-Date -Format 'yyyyMMdd_HHmmss'))
Write-Host "Logging to $log"

# Record everything and keep streaming output in the console
Start-Transcript -Path $log -Append | Out-Null
try {
    & python -u .\live_start.py
    $code = $LASTEXITCODE
    Write-Host "Python exited with code $code"
}
finally {
    Stop-Transcript | Out-Null
    Write-Host "`n[done] Press Enter to close..."
    $null = Read-Host
}
