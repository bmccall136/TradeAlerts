# --- Console theme (match Live) ---
try {
  $raw = $Host.UI.RawUI
  $raw.BackgroundColor = 'Black'
  $raw.ForegroundColor = 'Gray'
  $raw.WindowTitle     = 'TradeAlerts'
  Clear-Host
} catch {}

$ErrorActionPreference = 'Continue'
Set-Location -Path 'C:\TradeAlerts'

# --- Config file -> env var (underscore!) ---
$cfg = 'C:\TradeAlerts\sell_guard_settings.json'
if (-not (Test-Path $cfg)) {
  $alt = 'C:\TradeAlerts\sell_guard.settings.json'
  if (Test-Path $alt) { $cfg = $alt }
}
$env:SELL_GUARD_SETTINGS = $cfg
Write-Host "Using SELL_GUARD_SETTINGS=$($env:SELL_GUARD_SETTINGS)"
if (-not (Test-Path $cfg)) {
  Write-Host "WARNING: $cfg not found; sell_guard.py will fall back to live_settings.json" -ForegroundColor Yellow
}

# --- Logging + PID file ---
$logDir  = 'C:\TradeAlerts\logs'
$pidsDir = 'C:\TradeAlerts\pids'
New-Item -ItemType Directory -Path $logDir,$pidsDir -Force | Out-Null
$log    = Join-Path $logDir  'StartSellGuard.log'
$pidFile= Join-Path $pidsDir 'sell_guard.pid'

Start-Transcript -Path $log -Append | Out-Null
Write-Host "=== $(Get-Date) START Sell Guard (PID-backed) ==="

# --- Find Python robustly ---
function Resolve-Python([string[]]$candidates) {
  foreach ($p in $candidates) { if ($p -and (Test-Path $p)) { return $p } }
  try { $c = Get-Command python -ErrorAction Stop; if ($c -and (Test-Path $c.Path)) { return $c.Path } } catch {}
  try { $c = Get-Command py -ErrorAction Stop; if ($c) { return $c.Path } } catch {}
  return $null
}
$candidates = @(
  'C:\Users\bmccall\AppData\Local\Programs\Python\Python311\python.exe',
  'C:\Program Files\Python311\python.exe',
  'C:\Program Files\Python312\python.exe',
  'C:\Python311\python.exe'
)
$py = Resolve-Python $candidates
if (-not $py) {
  Write-Host "ERROR: Could not find Python. Edit Start-Sell-Guard.ps1 and set `$py manually." -ForegroundColor Red
  Write-Host "Press Enter to close."; [void](Read-Host); Stop-Transcript | Out-Null; exit 1
}

Write-Host "Python: $py"
Write-Host "CWD: $((Get-Location).Path)"
if (Test-Path $pidFile) { Remove-Item $pidFile -Force -ErrorAction SilentlyContinue }

# --- Launch sell_guard.py in the SAME window (splatting avoids -PassThru parsing issues) ---
try {
  Write-Host "Launching: $py -u .\sell_guard.py (same window)"
  $sp = @{
    FilePath         = $py
    ArgumentList     = @('-u','.\sell_guard.py')
    WorkingDirectory = 'C:\TradeAlerts'
    NoNewWindow      = $true
    PassThru         = $true
  }
  $p = Start-Process @sp
  if ($p -and $p.Id) {
    $p.Id | Out-File -FilePath $pidFile -Encoding ascii -Force
    Write-Host "Recorded PID $($p.Id) -> $pidFile"
  }
  Wait-Process -Id $p.Id
} catch {
  Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
  # minimal fallback if Start-Process ever misbehaves:
  try { & $py -u .\sell_guard.py } catch { Write-Host "Fallback failed: $($_.Exception.Message)" -ForegroundColor Red }
}

Write-Host "=== $(Get-Date) END Sell Guard ==="
Stop-Transcript | Out-Null

Write-Host "`n--------------------------------------------------"
Write-Host "Window will stay open. Close it when you are done." -ForegroundColor Yellow
Write-Host "Press Ctrl+C or click the close [X] to exit." -ForegroundColor Yellow
while ($true) { Start-Sleep -Seconds 3600 }
