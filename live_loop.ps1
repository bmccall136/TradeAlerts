# --- TradeAlerts PowerShell launcher ---
# Run: powershell -ExecutionPolicy Bypass -File .\start_live.ps1

$ErrorActionPreference = 'Stop'

# Working directory
$workDir = 'C:\TradeAlerts'
Set-Location $workDir

# --- Mode & guardrails ---
$env:BROKER_MODE           = 'LIVE'
$env:GUARDRAILS_ENABLED    = 'false'

# --- Safety / sizing (optional) ---
$env:LIVE_SAFE_MODE        = 'false'
$env:LIVE_MAX_QTY          = '1'
$env:LIVE_BP_BUFFER        = '10'
$env:LIVE_TPLUS_DAYS       = '0'
$env:LIVE_CANDIDATE_LOG_LIMIT = '120'

# --- One-run override to ignore buy gate (use only for testing) ---
# $env:LIVE_IGNORE_GUARDRAILS_TODAY = '1'

# Help Python/console handle unicode nicely
$env:PYTHONIOENCODING = 'utf-8'

# Command that the NEW window will run
$inner = @'
$host.UI.RawUI.WindowTitle = "TradeAlerts Live"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Set-Location "C:\TradeAlerts"
python -u .\live_start.py
Read-Host -Prompt "[done] Press Enter to close..."
'@

# Launch a NEW PowerShell window that stays open
Start-Process -FilePath 'powershell.exe' `
  -ArgumentList '-NoLogo','-NoExit','-ExecutionPolicy','Bypass','-Command', $inner `
  -WorkingDirectory $workDir
