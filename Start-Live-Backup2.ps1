# --- Console theme (match Live) ---
try {
  $raw = $Host.UI.RawUI
  $raw.BackgroundColor = 'Black'
  $raw.ForegroundColor = 'Gray'
  $raw.WindowTitle     = 'TradeAlerts — Buy Guard (RTH Only)'
  Clear-Host
} catch {}

$ErrorActionPreference = 'Continue'
Set-Location -Path 'C:\TradeAlerts'

# --- Config file -> env var (underscore!) ---
$cfg = 'C:\TradeAlerts\buy_guard_settings.json'
if (-not (Test-Path $cfg)) {
  $alt = 'C:\TradeAlerts\buy_guard.settings.json'
  if (Test-Path $alt) { $cfg = $alt }
}
$env:TRADEALERTS_BUY_GUARD_SETTINGS = $cfg

# --- Python path ---
$py = (Get-Command python -ErrorAction SilentlyContinue)?.Source
if (-not $py) { $py = (Get-Command py -ErrorAction SilentlyContinue)?.Source }
if (-not $py) { throw "Python not found in PATH." }

# --- Logging ---
$logDir = 'C:\TradeAlerts\logs\BuyGuard'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$stamp  = Get-Date -Format 'yyyy-MM-dd_HH-mm-ss'
$log    = Join-Path $logDir "buy_guard_$stamp.log"
Start-Transcript -Path $log -Append | Out-Null

Write-Host "=== $(Get-Date) START Buy Guard ==="
try {
  $args = @(
    '-u', '.\buy_guard.py'
  )
  $p = Start-Process -FilePath $py -ArgumentList $args -PassThru -NoNewWindow
  Wait-Process -Id $p.Id
} catch {
  Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
  try { & $py -u .\buy_guard.py } catch { Write-Host "Fallback failed: $($_.Exception.Message)" -ForegroundColor Red }
}

Write-Host "=== $(Get-Date) END Buy Guard ==="
Stop-Transcript | Out-Null

Write-Host "`n--------------------------------------------------"
Write-Host "Window will stay open. Close it when you are done." -ForegroundColor Yellow
Write-Host "Press Ctrl+C or click the close [X] to exit." -ForegroundColor Yellow
while ($true) { Start-Sleep -Seconds 3600 }
