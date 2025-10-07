# Start-Dashboard.ps1 — simple, debug-friendly launcher
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

# Work from this folder
Set-Location -Path $PSScriptRoot

# Find a Python executable: venv first, then py, then python
$exe = $null
$venvPy = Join-Path $PSScriptRoot 'venv\Scripts\python.exe'
if (Test-Path $venvPy) {
  $exe = $venvPy
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
  $exe = 'py'
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
  $exe = 'python'
}

if (-not $exe) {
  Write-Host "❌ Python not found. Install Python or create .\venv" -ForegroundColor Red
  Read-Host "Press Enter to close"
  exit 1
}

# Verify dashboard.py exists
$dashboard = Join-Path $PSScriptRoot 'dashboard.py'
if (-not (Test-Path $dashboard)) {
  Write-Host "❌ dashboard.py not found at $dashboard" -ForegroundColor Red
  Read-Host "Press Enter to close"
  exit 1
}

# Build args
$args = @()
if ($exe -ieq 'py') { $args += '-3' }   # prefer Python 3 via 'py'
$args += '-u', $dashboard                # -u = unbuffered so logs show immediately

Write-Host ""
Write-Host "➡️  Launching: $exe $($args -join ' ')" -ForegroundColor Cyan
Write-Host ""

try {
  & $exe @args
} catch {
  Write-Host "❌ Launch failed: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""
Read-Host "Dashboard exited (or crashed). Press Enter to close"
