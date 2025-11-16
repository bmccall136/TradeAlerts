param(
    [string]$Mode = $null
)

# Always work from the TradeAlerts root
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "=== TradeAlerts – Start Sell Guard ==="

# ----------------- 1) Resolve mode (DAY / SWING) -----------------
$liveModeFile = Join-Path $root 'live_mode.txt'

if (-not $Mode) {
    if (Test-Path $liveModeFile) {
        $Mode = (Get-Content $liveModeFile -Raw).Trim().ToUpper()
        if (-not $Mode) { $Mode = 'SWING' }
    }
    else {
        $Mode = 'SWING'
    }
} else {
    $Mode = $Mode.Trim().ToUpper()
}

if ($Mode -ne 'DAY' -and $Mode -ne 'SWING') {
    Write-Warning "Unknown mode '$Mode' – defaulting to SWING."
    $Mode = 'SWING'
}

# ----------------- 2) Pick settings file for this mode -----------------
$baseCfg = Join-Path $root 'sell_guard_settings.json'
$dayCfg  = Join-Path $root 'sell_guard_settings_day.json'
$swingCfg= Join-Path $root 'sell_guard_settings_swing.json'

$cfg = $baseCfg

if ($Mode -eq 'DAY' -and (Test-Path $dayCfg)) {
    $cfg = $dayCfg
}
elseif ($Mode -eq 'SWING' -and (Test-Path $swingCfg)) {
    $cfg = $swingCfg
}
elseif (Test-Path $baseCfg) {
    $cfg = $baseCfg
}

$env:SELL_GUARD_SETTINGS = $cfg
Write-Host "Mode $Mode → SELL_GUARD_SETTINGS=$($env:SELL_GUARD_SETTINGS)"

if (-not (Test-Path $cfg)) {
    Write-Warning "Config file $cfg not found. sell_guard.py will start with no settings!"
}

# ----------------- 3) Launch sell_guard.py -----------------
$python = "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

Write-Host "Launching: $python -u sell_guard.py"
& $python -u "sell_guard.py"

Write-Host ""
Write-Host "--------------------------------------------------"
Write-Host "Sell Guard exited. Close this window when done."
