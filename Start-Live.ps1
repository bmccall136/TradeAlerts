# TradeAlerts — LIVE (Buy Loop)
$ErrorActionPreference = 'Continue'
try { $Host.UI.RawUI.WindowTitle = 'TradeAlerts — LIVE (Buy Loop)'; Clear-Host } catch {}

$root   = 'C:\TradeAlerts'
$script = Join-Path $root 'live_start.py'        # <— your real live entrypoint
$cfg    = Join-Path $root 'live_settings.json'
$logDir = Join-Path $root 'logs'
$pidDir = Join-Path $root 'pids'
New-Item -ItemType Directory -Path $logDir,$pidDir -Force | Out-Null
Set-Location -Path $root

# Find Python (PowerShell 5.1 safe)
$py = $null
try { $py = (Get-Command python -ErrorAction Stop).Source } catch {
  try { $py = (Get-Command py -ErrorAction Stop).Source } catch {
    $py = 'C:\Users\bmccall\AppData\Local\Programs\Python\Python311\python.exe'
    if (-not (Test-Path $py)) { Write-Host "Python not found." -ForegroundColor Red; exit 1 }
  }
}
Write-Host "Python: $py"
Write-Host "CWD: $((Get-Location).Path)"

# Log transcript
$log = Join-Path $logDir 'Start-Live.log'
try { Start-Transcript -Path $log -Append -ErrorAction SilentlyContinue | Out-Null } catch {}

# Environment (match your live code)
$env:ETRADE_ENV                = 'production'
$env:PYTHONUNBUFFERED          = '1'
$env:PYTHONIOENCODING          = 'utf-8'
$env:LIVE_SETTINGS             = $cfg                  # legacy var some code reads
$env:TRADEALERTS_LIVE_SETTINGS = $cfg                  # newer name (harmless if unused)

# --- Explicit overrides for Monday ---
$env:GUARDRAILS_ENABLED = 'false'
$env:LIVE_SAFE_MODE     = 'false'
$env:GR_AUTO_SELLER     = '0'

Write-Host "Launching: $py -u `"$script`""
try {
  & $py -u $script
} catch {
  Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
} finally {
  try { Stop-Transcript | Out-Null } catch {}
}

Write-Host "`n--------------------------------------------------"
Write-Host "Window will stay open. Close it when you are done." -ForegroundColor Yellow
while ($true) { Start-Sleep -Seconds 3600 }
