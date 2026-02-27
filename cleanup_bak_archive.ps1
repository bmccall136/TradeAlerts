param(
  [string]$Root = "C:\TradeAlerts\_bak_archive",
  [int]$KeepPerBase = 10,
  [int]$MaxAgeDays = 0,
  [switch]$WhatIf
)

$ErrorActionPreference = "Stop"

function Count-Any($x) {
  if ($null -eq $x) { return 0 }
  return ($x | Measure-Object).Count
}

function Get-BaseKey([string]$Name) {
  # group "analytics_buy.html.bak_add_..." under "analytics_buy.html"
  $m = [regex]::Match($Name, '^(?<base>.+?)\.bak', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
  if ($m.Success) { return $m.Groups['base'].Value }
  return $null
}

if (!(Test-Path -LiteralPath $Root)) { throw "Path not found: $Root" }

Write-Host "=== $$Machine BAK Cleanup ==="
Write-Host "Root        : $Root"
Write-Host "KeepPerBase : $KeepPerBase"
Write-Host "MaxAgeDays  : $MaxAgeDays (0 means disabled)"
Write-Host "WhatIf      : $WhatIf"
Write-Host ""

# ONLY consider files that contain ".bak" anywhere in the filename
$bakFiles = Get-ChildItem -LiteralPath $Root -File -Recurse | Where-Object { $_.Name -match '\.bak' }

if ((Count-Any $bakFiles) -eq 0) {
  Write-Host "No .bak files found under $Root"
  exit 0
}

$items = $bakFiles |
  ForEach-Object {
    $base = Get-BaseKey $_.Name
    if ($base) { [pscustomobject]@{ Base=$base; File=$_ } }
  }

$groups = $items | Group-Object Base

$toDelete = New-Object System.Collections.Generic.List[System.IO.FileInfo]

foreach ($g in $groups) {
  $files = $g.Group | ForEach-Object { $_.File } | Sort-Object LastWriteTime -Descending
  $keep  = $files | Select-Object -First $KeepPerBase
  $drop  = $files | Select-Object -Skip  $KeepPerBase

  foreach ($f in $drop) { $toDelete.Add($f) }

  Write-Host ("{0,-35} total={1,4} keep={2,3} delete={3,4}" -f $g.Name, (Count-Any $files), (Count-Any $keep), (Count-Any $drop))
}

if ($MaxAgeDays -gt 0) {
  $cutoff = (Get-Date).AddDays(-1 * $MaxAgeDays)
  $old = $bakFiles | Where-Object { $_.LastWriteTime -lt $cutoff }
  foreach ($f in $old) { $toDelete.Add($f) }
  Write-Host ""
  Write-Host "Age cutoff: $cutoff"
  Write-Host ("Age-based candidates: {0}" -f (Count-Any $old))
}

$toDelete = $toDelete | Sort-Object FullName -Unique

Write-Host ""
Write-Host ("Delete candidates: {0}" -f (Count-Any $toDelete))

if ((Count-Any $toDelete) -eq 0) {
  Write-Host "Nothing to delete."
  exit 0
}

foreach ($f in $toDelete) {
  if ($WhatIf) {
    Write-Host ("WHATIF  del  {0}" -f $f.FullName)
  } else {
    Remove-Item -LiteralPath $f.FullName -Force
    Write-Host ("DELETED      {0}" -f $f.FullName)
  }
}

Write-Host ""
Write-Host "Done."
