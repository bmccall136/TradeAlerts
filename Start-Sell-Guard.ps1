# Start-Sell-Guard.ps1
# Launches sell_guard.py from this folder, writes logs, and records a PID file.
# Safe paths (no hardcoding), prefers local venv, UTF-8 output, PID hygiene.

# --- Console theme (match Live) ---
try {
  $raw = $Host.UI.RawUI
  $raw.BackgroundColor = 'Black'
  $raw.ForegroundColor = 'Gray'
  $raw.WindowTitle     = 'TradeAlerts'
  Clear-Host
} catch {}

# --- Encoding + unbuffered python output ---
try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false) } catch {}
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUNBUFFERED = '1'

$ErrorActionPreference = 'Continue'

# Work out of the script's folder
Set-Location -Path $PSScriptRoot

# --- Config file -> env var (underscore!) ---
$cfg = Join-Path $PSScriptRoot 'sell_guard_settings.json'
if (-not (Test-Path $cfg)) {
  $alt = Join-Path $PSScriptRoot 'sell_guard.settings.json'
  if (Test-Path $alt) { $cfg = $alt }
}
$env:SELL_GUARD_SETTINGS = $cfg
Write-Host "Using SELL_GUARD_SETTINGS=$($env:SELL_GUARD_SETTINGS)"
if (-not (Test-Path $cfg)) {
  Write-Host "WARNING: $cfg not found; sell_guard.py will fall back to live_settings.json" -ForegroundColor Yellow
}

# --- Logging + PID file ---
$logDir  = Join-Path $PSScriptRoot 'logs'
$pidsDir = Join-Path $PSScriptRoot 'pids'
New-Item -ItemType Directory -Path $logDir,$pidsDir -Force | Out-Null
$log     = Join-Path $logDir  'StartSellGuard.log'
$pidFile = Join-Path $pidsDir 'sell_guard.pid'

Start-Transcript -Path $log -Append | Out-Null
Write-Host "=== $(Get-Date) START Sell Guard (PID-backed) ==="

# --- Find Python robustly (prefer venv) ---
function Resolve-Python([string[]]$candidates) {
  foreach ($p in $candidates) {
    if ($p -and (Test-Path $p)) { return $p }
  }
  try { $c = Get-Command python -ErrorAction Stop; if ($c -and (Test-Path $c.Path)) { return $c.Path } } catch {}
  try { $c = Get-Command py -ErrorAction Stop; if ($c) { return $c.Path } } catch {}
  return $null
}

$venvPy = Join-Path $PSScriptRoot 'venv\Scripts\python.exe'
$candidates = @(
  $venvPy,
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

# Clear any stale PID file
if (Test-Path $pidFile) { Remove-Item $pidFile -Force -ErrorAction SilentlyContinue }

# --- Launch sell_guard.py in the SAME window (splatting avoids -PassThru parsing issues) ---
try {
  Write-Host "Launching: $py -u .\sell_guard.py (same window)"
  $sp = @{
    FilePath         = $py
    ArgumentList     = @('-u','.\sell_guard.py')
    WorkingDirectory = $PSScriptRoot
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
  # Minimal fallback if Start-Process ever misbehaves:
  try { & $py -u .\sell_guard.py } catch { Write-Host "Fallback failed: $($_.Exception.Message)" -ForegroundColor Red }
} finally {
  # Remove PID file on exit so no stale PID lingers
  if (Test-Path $pidFile) {
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
  }
}

Write-Host "=== $(Get-Date) END Sell Guard ==="
Stop-Transcript | Out-Null

Write-Host "`n--------------------------------------------------"
Write-Host "Done. Press Enter to close..." -ForegroundColor Yellow
[void](Read-Host)
