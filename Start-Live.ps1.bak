# --- Console theme ---
try {
    $raw = $Host.UI.RawUI
    $raw.BackgroundColor = 'Black'    # background
    $raw.ForegroundColor = 'Gray'     # text color (use 'White' if you prefer)
    $raw.WindowTitle     = 'TradeAlerts'  # optional: custom title
    Clear-Host
} catch {}

$ErrorActionPreference = 'Continue'
Set-Location -Path 'C:\TradeAlerts'
$logDir = Join-Path -Path 'C:\TradeAlerts' -ChildPath 'logs'
if (-not (Test-Path $logDir)) { New-Item -Path $logDir -ItemType Directory -Force | Out-Null }
$log = Join-Path -Path $logDir -ChildPath 'StartLive-NoGuards.log'
Start-Transcript -Path $log -Append | Out-Null

Write-Host "=== $(Get-Date) START Start Live (NO GUARDS) ==="
Write-Host "Python: C:\Users\bmccall\AppData\Local\Programs\Python\Python311\python.exe"
Write-Host "CWD: $((Get-Location).Path)"

# Force guardrails OFF for this session
$env:GUARDRAILS_ENABLED = 'false'
$env:LIVE_SAFE_MODE = 'false'
$env:GR_AUTO_SELLER = '0'
$env:LIVE_ARMED = '1'  # optional: allow actions if your code checks this

Write-Host "Env GUARDRAILS_ENABLED=$($env:GUARDRAILS_ENABLED)"
Write-Host "Env LIVE_SAFE_MODE=$($env:LIVE_SAFE_MODE)"
Write-Host "Env GR_AUTO_SELLER=$($env:GR_AUTO_SELLER)"
Write-Host "Env LIVE_ARMED=$($env:LIVE_ARMED)"

try {
    & 'C:\Users\bmccall\AppData\Local\Programs\Python\Python311\python.exe' -u '.\live_start.py'
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host $_.Exception | Format-List -Force
}
Write-Host "=== $(Get-Date) END Start Live (NO GUARDS) ==="
Stop-Transcript | Out-Null

Write-Host ''
Write-Host '--------------------------------------------------'
Write-Host 'Window will stay open. Close it when you are done.' -ForegroundColor Yellow
Write-Host 'Press Ctrl+C or click the close [X] to exit.' -ForegroundColor Yellow
while ($true) { Start-Sleep -Seconds 3600 }
