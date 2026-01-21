# Start-Dashboard.ps1 — simple, debug-friendly launcher (FORCES .\.venv)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

Set-Location -Path $PSScriptRoot

# FORCE venv python (project standard: .\.venv)
$exe = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'

if (-not (Test-Path $exe)) {
  Write-Host "❌ .\.venv\Scripts\python.exe not found. Create venv first:" -ForegroundColor Red
  Write-Host "   py -3 -m venv .venv" -ForegroundColor Yellow
  Write-Host "   .\.venv\Scripts\python.exe -m pip install -r requirements.txt" -ForegroundColor Yellow
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

Write-Host ""
Write-Host "➡️  Launching: $exe -u $dashboard" -ForegroundColor Cyan
Write-Host ""

try {
  & $exe -u $dashboard
} catch {
  Write-Host "❌ Launch failed: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""
Read-Host "Dashboard exited (or crashed). Press Enter to close"
