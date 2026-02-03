param(
  [string]$Root = "C:\TradeAlerts\logs"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Backup-File([string]$Path) {
  $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
  $bak = "$Path.bak_$stamp"
  Copy-Item -LiteralPath $Path -Destination $bak -Force
  Write-Host "Backup -> $bak"
}

function Get-EasternOffset([datetime]$Dt) {
  $tz = [TimeZoneInfo]::FindSystemTimeZoneById("Eastern Standard Time")
  return $tz.GetUtcOffset($Dt)
}

function Normalize-BuyFile([string]$Path) {
  $rows = Import-Csv -LiteralPath $Path
  if ($rows.Count -eq 0) { return }

  $needsWrite = $false

  $out = foreach ($r in $rows) {
    $hasTimeEt = ($r.PSObject.Properties.Name -contains "time_et")
    if (-not $hasTimeEt -or [string]::IsNullOrWhiteSpace($r.time_et)) { $r; continue }

    $hasTsEt = ($r.PSObject.Properties.Name -contains "ts_et")
    if ($hasTsEt -and -not [string]::IsNullOrWhiteSpace($r.ts_et)) { $r; continue }

    # time_et: "yyyy-MM-dd HH:mm:ss"
    try {
      $dt  = [datetime]::ParseExact($r.time_et, "yyyy-MM-dd HH:mm:ss", [System.Globalization.CultureInfo]::InvariantCulture)
      $off = Get-EasternOffset $dt
      $dto = [datetimeoffset]::new($dt, $off)
      $r | Add-Member -NotePropertyName "ts_et" -NotePropertyValue ($dto.ToString("yyyy-MM-ddTHH:mm:sszzz")) -Force
      $needsWrite = $true
    } catch {
      # leave row unchanged if parse fails
    }

    $r
  }

  if ($needsWrite) {
    Backup-File $Path
    $out | Export-Csv -LiteralPath $Path -NoTypeInformation
    Write-Host "Normalized BUY -> $Path"
  }
}

function Normalize-SellFile([string]$Path) {
  $rows = Import-Csv -LiteralPath $Path
  if ($rows.Count -eq 0) { return }

  $needsWrite = $false

  $out = foreach ($r in $rows) {
    $hasTimeEt = ($r.PSObject.Properties.Name -contains "time_et")
    if ($hasTimeEt -and -not [string]::IsNullOrWhiteSpace($r.time_et)) { $r; continue }

    $raw = $null
    if ($r.PSObject.Properties.Name -contains "ts_et" -and -not [string]::IsNullOrWhiteSpace($r.ts_et)) {
      $raw = $r.ts_et
    } elseif ($r.PSObject.Properties.Name -contains "ts_utc" -and -not [string]::IsNullOrWhiteSpace($r.ts_utc)) {
      $raw = $r.ts_utc
    } else {
      $r
      continue
    }

    try {
      $dto = [datetimeoffset]::Parse($raw, [System.Globalization.CultureInfo]::InvariantCulture)
      $r | Add-Member -NotePropertyName "time_et" -NotePropertyValue ($dto.ToString("yyyy-MM-dd HH:mm:ss")) -Force
      $needsWrite = $true
    } catch {
      # leave row unchanged if parse fails
    }

    $r
  }

  if ($needsWrite) {
    Backup-File $Path
    $out | Export-Csv -LiteralPath $Path -NoTypeInformation
    Write-Host "Normalized SELL -> $Path"
  }
}

if (!(Test-Path -LiteralPath $Root)) { throw "Logs folder not found: $Root" }

$buyFiles = Get-ChildItem -LiteralPath $Root -Filter "triggers_*.csv" -File |
            Where-Object { $_.Name -notlike "sell_triggers_*" }

$sellFiles = Get-ChildItem -LiteralPath $Root -Filter "sell_triggers_*.csv" -File

Write-Host ("BUY files : {0}" -f $buyFiles.Count)
Write-Host ("SELL files: {0}" -f $sellFiles.Count)

foreach ($f in $buyFiles)  { Normalize-BuyFile  $f.FullName }
foreach ($f in $sellFiles) { Normalize-SellFile $f.FullName }

Write-Host "Done. Refresh Trade Review."
