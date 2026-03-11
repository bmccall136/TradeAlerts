# C:\TradeAlerts\run_live.ps1
$ErrorActionPreference = 'Stop'
$Host.UI.RawUI.WindowTitle = 'TradeAlerts Live (PowerShell)'

# --- Env you wanted ---
$env:BROKER_MODE = 'LIVE'
$env:GUARDRAILS_ENABLED = 'false'
$env:LIVE_SAFE_MODE = 'false'
$env:LIVE_MAX_QTY = '1'
$env:LIVE_IGNORE_GUARDRAILS_TODAY = '1'   # gate open

# Optional: shrink BP buffer (or 0) so small BP can buy at least 1 share
$env:LIVE_BP_BUFFER = '0'

# Optional: crash handling signal to your code if you want
$env:HOLD_ON_CRASH = '1'

Set-Location 'C:\TradeAlerts'
New-Item -Type Directory -Force -Path '.\logs' | Out-Null

while ($true) {
    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $log   = Join-Path .\logs "live_$stamp.log"

    Write-Host "▶ starting live_start.py (logging to $log)..." -ForegroundColor Cyan
    # -u = unbuffered, Tee keeps output in the console AND the file
    python -u .\live_start.py *>&1 | Tee-Object -FilePath $log
    $code = $LASTEXITCODE

    if ($code -ne 0) {
        Write-Host "`nPython exited with code $code" -ForegroundColor Red
        Write-Host "Last lines of log:" -ForegroundColor DarkGray
        Get-Content $log -Tail 30
        $ans = Read-Host "`nPress <Enter> to restart, or type Q to quit"
        if ($ans -match '^[Qq]$') { break }
        continue
    } else {
        Read-Host "`nPython exited normally. Press <Enter> to close"
        break
    }
}
