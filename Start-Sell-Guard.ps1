# C:\TradeAlerts\Start-Sell-Guard.ps1
# Launch Sell Guard using the mode selected by the UI (live_mode.txt),
# unless -Mode is explicitly provided.

param(
  [ValidateSet("DAY","SWING")]
  [string]$Mode = ""
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=== TradeAlerts – Start Sell Guard ===" -ForegroundColor Cyan

$root = Split-Path -Parent $MyInvocation.MyCommand.Path

# --- Load env vars from etrade.env if present (guarantees NAV_FLOOR_BUY_BLOCK) ---
$envFile = Join-Path $root "etrade.env"
if (Test-Path $envFile) {
  Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#") -or ($line -notmatch "=")) { return }
    $k, $v = $line.Split("=", 2)
    $k = $k.Trim()
    $v = $v.Trim().Trim('"').Trim("'")
    if ($k) { Set-Item -Path ("Env:\" + $k) -Value $v }
  }
}

# Hard floor for kids' money — override here if you ever need to
if (-not $env:NAV_FLOOR_BUY_BLOCK) { $env:NAV_FLOOR_BUY_BLOCK = "4000" }

$py = Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"
if (-not (Test-Path $py)) {
  # fallback: whatever python is in PATH
  $py = "python"
}

# --- Read UI-selected mode from live_mode.txt if -Mode wasn't provided ---
$modeFile = Join-Path $root "live_mode.txt"
if ([string]::IsNullOrWhiteSpace($Mode)) {
  if (Test-Path $modeFile) {
    try {
      $m = (Get-Content $modeFile -Raw).Trim().ToUpper()
      if ($m -eq "DAY" -or $m -eq "SWING") {
        $Mode = $m
      }
    } catch {
      # ignore and fall back
    }
  }
}

if ([string]::IsNullOrWhiteSpace($Mode)) {
  $Mode = "DAY"
}

# --- Pick config based on Mode ---
$baseCfg  = Join-Path $root "sell_guard_settings.json"
$dayCfg   = Join-Path $root "sell_guard_settings_day.json"
$swingCfg = Join-Path $root "sell_guard_settings_swing.json"

$cfg = $baseCfg
if ($Mode -eq "DAY" -and (Test-Path $dayCfg)) { $cfg = $dayCfg }
elseif ($Mode -eq "SWING" -and (Test-Path $swingCfg)) { $cfg = $swingCfg }

$env:SELL_GUARD_SETTINGS = $cfg
Write-Host "Mode $Mode → SELL_GUARD_SETTINGS=$($env:SELL_GUARD_SETTINGS)" -ForegroundColor Yellow

if (-not (Test-Path $cfg)) {
  Write-Warning "Config file $cfg not found. sell_guard.py will start with defaults!"
}

$script = Join-Path $root "sell_guard.py"
if (-not (Test-Path $script)) {
  throw "sell_guard.py not found at $script"
}

Write-Host "Launching: $py -u $script" -ForegroundColor Green
& $py -u $script
