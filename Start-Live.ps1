# --- Console theme (optional) ---
try {
    $raw = $Host.UI.RawUI
    $raw.BackgroundColor = 'Black'
    $raw.ForegroundColor = 'Gray'
    $raw.WindowTitle     = 'TradeAlerts — Sell Guard (RTH Only)'
    Clear-Host
} catch {}

# --- Paths ---
$root   = 'C:\TradeAlerts'
$py     = 'C:\Users\bmccall\AppData\Local\Programs\Python\Python311\python.exe'
$script = Join-Path $root 'sell_guard.py'
$cfg    = Join-Path $root 'sell_guard_settings.json'
$logDir = Join-Path $root 'logs'
$pidDir = Join-Path $root 'pids'
$pidFile= Join-Path $pidDir 'sell_guard.pid'
New-Item -ItemType Directory -Path $logDir,$pidDir -Force | Out-Null

# --- Log transcript ---
$log = Join-Path $logDir ("StartSellGuard-RTH.log")
Start-Transcript -Path $log -Append | Out-Null

Write-Host "=== $(Get-Date) START Sell Guard (RTH-only / No Day Trades / No Intraday) ==="
Write-Host "Python: $py"
Set-Location -Path $root
Write-Host "CWD: $((Get-Location).Path)"

# --- Environment (explicit, safe) ---
$env:ETRADE_ENV            = 'production'
$env:PYTHONPATH            = $null
$env:SELL_GUARD_SETTINGS   = $cfg   # tell the guard exactly which settings to use

# DO NOT disable guardrails; we honor the JSON:
#   use_extended_hours=false
#   avoid_daytrades=true
#   allow_intraday_stoploss=false
#   sell window 09:35–15:55 ET
Write-Host "Using SELL_GUARD_SETTINGS=$($env:SELL_GUARD_SETTINGS)"

# --- Single-instance protection (PID file) ---
if (Test-Path $pidFile) {
    try {
        $oldPid = Get-Content $pidFile -ErrorAction Stop | Select-Object -First 1
        if ($oldPid -and (Get-Process -Id $oldPid -ErrorAction SilentlyContinue)) {
            Write-Host "Another Sell Guard appears to be running (PID $oldPid). Exiting." -ForegroundColor Yellow
            Stop-Transcript | Out-Null
            return
        } else {
            Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
        }
    } catch {
        Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    }
}

# --- Launch guard (same window, unbuffered output) ---
try {
    Write-Host "Launching: $py -u `"$script`""
    & $py -u $script
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host $_.Exception | Format-List -Force
} finally {
    # Best-effort cleanup; guard itself should also manage the PID
    if (Test-Path $pidFile) { Remove-Item $pidFile -Force -ErrorAction SilentlyContinue }
}

Write-Host "=== $(Get-Date) END Sell Guard (RTH-only) ==="
Stop-Transcript | Out-Null

Write-Host ''
Write-Host '--------------------------------------------------'
Write-Host 'Window will stay open. Close it when you are done.' -ForegroundColor Yellow
Write-Host 'Press Ctrl+C or click the close [X] to exit.' -ForegroundColor Yellow
while ($true) { Start-Sleep -Seconds 3600 }
