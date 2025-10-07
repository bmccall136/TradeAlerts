$ErrorActionPreference = "Continue"
Set-Location -Path "C:\TradeAlerts"

$logDir  = Join-Path "C:\TradeAlerts" "logs"
$pidsDir = Join-Path "C:\TradeAlerts" "pids"
if (-not (Test-Path $logDir))  { New-Item -ItemType Directory -Path $logDir  -Force | Out-Null }
if (-not (Test-Path $pidsDir)) { New-Item -ItemType Directory -Path $pidsDir -Force | Out-Null }
$log = Join-Path $logDir "StopAll.log"
Start-Transcript -Path $log -Append | Out-Null
Write-Host "=== $(Get-Date) STOP ALL (fixed live) ==="

function Kill-ById([int]$procId,[string]$label) {
  if ($procId -le 0) { return $false }
  try {
    Write-Host "Killing $label PID $procId"
    Stop-Process -Id $procId -Force -ErrorAction Stop
    return $true
  } catch {
    try { & taskkill /PID $procId /T /F | Out-Null; Write-Host "taskkill tree for $label $procId issued."; return $true }
    catch { Write-Host "ERROR: failed to kill $label $procId -> $($_.Exception.Message)" -ForegroundColor Red; return $false }
  }
}

$kPy = 0; $kPS = 0

# 1) PID files (precise)
foreach ($pf in @("sell_guard.pid","live.pid")) {
  $full = Join-Path $pidsDir $pf
  if (Test-Path $full) {
    $pidText = Get-Content $full -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($pidText -match '^\d+$') { if (Kill-ById ([int]$pidText) $pf) { $kPy++ } }
    Remove-Item $full -Force -ErrorAction SilentlyContinue
  }
}

# 2) Python by explicit command-line patterns (covers LIVE and SELL)
$py = Get-CimInstance Win32_Process | Where-Object {
  $_.Name -match '^python(\.exe)?$' -and (
       $_.CommandLine -match 'live_start\.py'                     -or
       $_.CommandLine -match '-m\s+live_start'                    -or
       $_.CommandLine -match 'services[\\/]+live_guardrails\.py'  -or
       $_.CommandLine -match '-m\s+services\.live_guardrails'     -or
       $_.CommandLine -match 'sell[_\-]?guard'                    -or
       $_.CommandLine -match 'services[\\/]+sell_guard\.py'       -or
       $_.CommandLine -match '-m\s+services\.sell_guard'
  )
}
foreach ($p in $py) { if (Kill-ById $p.ProcessId "python(cmdline)") { $kPy++ } }

# 3) PowerShell launcher windows that started from C:\TradeAlerts
$ps = Get-CimInstance Win32_Process | Where-Object {
  $_.Name -match 'powershell|pwsh' -and $_.CommandLine -match 'C:\\TradeAlerts' -and $_.CommandLine -match '-File'
}
foreach ($p in $ps) { if (Kill-ById $p.ProcessId "powershell(cmdline)") { $kPS++ } }

Write-Host ""
Write-Host "Summary: killed python=$kPy, powershell=$kPS"
Write-Host "Log: $log"
Stop-Transcript | Out-Null
Write-Host ""
Write-Host "Press Enter to close this window."
[void](Read-Host)
