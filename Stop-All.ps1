# --- Console theme ---
try {
    $raw = $Host.UI.RawUI
    $raw.BackgroundColor = 'Black'    # background
    $raw.ForegroundColor = 'Gray'     # text color (use 'White' if you prefer)
    $raw.WindowTitle     = 'TradeAlerts'  # optional: custom title
    Clear-Host
} catch {}

$ErrorActionPreference = 'Continue'
Set-Location -Path 'C:\TradeAlerts'

# --- logging dirs
$logDir  = Join-Path -Path 'C:\TradeAlerts' -ChildPath 'logs'
$pidsDir = Join-Path -Path 'C:\TradeAlerts' -ChildPath 'pids'
if (-not (Test-Path $logDir))  { New-Item -Path $logDir  -ItemType Directory -Force | Out-Null }
if (-not (Test-Path $pidsDir)) { New-Item -Path $pidsDir -ItemType Directory -Force | Out-Null }
$log = Join-Path -Path $logDir -ChildPath 'StopAll.log'
Start-Transcript -Path $log -Append | Out-Null
Write-Host '=== ' (Get-Date) ' STOP ALL (super-clean) ==='

function Kill-ById {
    param([int]$procId, [string]$label)
    if ($null -eq $procId -or $procId -le 0) { return $false }
    try {
        Write-Host 'Killing ' $label ' PID ' $procId
        Stop-Process -Id $procId -Force -ErrorAction Stop
        return $true
    } catch {
        Write-Host 'WARN: Failed to kill ' $label ' PID ' $procId ' - ' $_.Exception.Message
        try {
            & taskkill /PID $procId /T /F | Out-Null
            Write-Host 'taskkill tree for ' $label ' PID ' $procId ' issued.'
            return $true
        } catch {
            Write-Host 'ERROR: taskkill failed for ' $label ' PID ' $procId
            return $false
        }
    }
}

$killedPy = 0
$killedPS = 0

# 1) PID files (sell_guard, live) first
$pidFiles = @('sell_guard.pid','live.pid')
foreach ($pf in $pidFiles) {
  $full = Join-Path -Path $pidsDir -ChildPath $pf
  if (Test-Path $full) {
    $pidText = Get-Content $full -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($pidText -match '^\d+$') {
      if (Kill-ById ([int]$pidText) $pf) { $killedPy++ }
    }
    Remove-Item $full -Force -ErrorAction SilentlyContinue
  }
}

# 2) python processes by cmdline match
$pyMatches = Get-CimInstance Win32_Process | Where-Object {
  $_.Name -match '^python(\.exe)?$' -and (
    $_.CommandLine -match 'live_start\.py' -or
    $_.CommandLine -match 'services[\\/]+sell_guard\.py' -or
    $_.CommandLine -match '-m\s+services\.sell_guard' -or
    $_.CommandLine -match 'sell[_\-]?guard'
  )
}
foreach ($p in $pyMatches) {
  if (Kill-ById $p.ProcessId 'python(cmdline)') { $killedPy++ }
}

# 3) powershell hosts by cmdline match
$psMatches = Get-CimInstance Win32_Process | Where-Object {
  $_.Name -match 'powershell|pwsh' -and (
    $_.CommandLine -match 'Start-Live' -or
    $_.CommandLine -match 'Start-Sell-Guard' -or
    $_.CommandLine -match 'keep-open'
  )
}
foreach ($p in $psMatches) {
  if (Kill-ById $p.ProcessId 'powershell(cmdline)') { $killedPS++ }
}

Write-Host 'Summary: killed python=' $killedPy ', powershell=' $killedPS
Write-Host ('Log: ' + $log)

Stop-Transcript | Out-Null
Write-Host ''
Write-Host 'Press Enter to close this window.'
Read-Host | Out-Null
