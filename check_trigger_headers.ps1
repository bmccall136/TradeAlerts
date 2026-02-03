param(
  [string]$Logs = "C:\TradeAlerts\logs"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Latest($pattern) {
  Get-ChildItem -LiteralPath $Logs -Filter $pattern -File |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
}

$buy  = Latest "triggers_*.csv"
$sell = Latest "sell_triggers_*.csv"

if (-not $buy)  { throw "No triggers_*.csv found in $Logs" }
if (-not $sell) { throw "No sell_triggers_*.csv found in $Logs" }

$buyHdr  = (Get-Content -LiteralPath $buy.FullName -TotalCount 1)
$sellHdr = (Get-Content -LiteralPath $sell.FullName -TotalCount 1)

Write-Host "BUY  latest: $($buy.Name)"
Write-Host "SELL latest: $($sell.Name)"

if ($buyHdr -notmatch 'time_et' -or $buyHdr -notmatch 'ts_et') {
  throw "BUY header missing time_et or ts_et: $buyHdr"
}
if ($sellHdr -notmatch 'ts_et' -or $sellHdr -notmatch 'time_et') {
  throw "SELL header missing ts_et or time_et: $sellHdr"
}

Write-Host "OK: headers are normalized."
