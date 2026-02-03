param(
  [string]$Path = "C:\TradeAlerts\sell_guard.py"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (!(Test-Path -LiteralPath $Path)) { throw "File not found: $Path" }

$src = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$bak = "$Path.bak_patch_time_et_$stamp"
Set-Content -LiteralPath $bak -Value $src -Encoding UTF8
Write-Host "Backup -> $bak"

# 1) Ensure DEFAULT_COLUMNS includes "time_et" right after "ts_et"
if ($src -notmatch 'DEFAULT_COLUMNS\s*=\s*[\[\(][\s\S]*?["'']time_et["'']') {
  $patCols = '(?s)(DEFAULT_COLUMNS\s*=\s*[\[\(][\s\S]*?["'']ts_et["'']\s*,\s*\n)'
  $repCols = '$1' + '    "time_et",' + "`n"
  $src2 = [regex]::Replace($src, $patCols, $repCols, 1)
  if ($src2 -eq $src) { throw 'Could not patch DEFAULT_COLUMNS (could not find "ts_et" inside DEFAULT_COLUMNS).' }
  $src = $src2
  Write-Host 'Patched DEFAULT_COLUMNS -> added "time_et"'
} else {
  Write-Host 'DEFAULT_COLUMNS already has "time_et"'
}

# 2) In emit_sell_event, set row["time_et"] right before w.writerow(row)
# Insert only if the function doesn't already set time_et somewhere
if ($src -notmatch 'def\s+emit_sell_event[\s\S]*?row\[\s*["'']time_et["'']\s*\]') {
  $patWrite = '(?s)(def\s+emit_sell_event[\s\S]*?\n)([\s\S]*?)(\n\s*w\.writerow\(\s*row\s*\))'
  $m = [regex]::Match($src, $patWrite)
  if (!$m.Success) { throw 'Could not locate emit_sell_event writerow(row) block.' }

  $inject = "`n            # Ensure Trade Review-friendly local timestamp`n" +
            '            row["time_et"] = row.get("time_et") or now_et.strftime("%Y-%m-%d %H:%M:%S")' + "`n"

  # Replace only the first writerow(row) inside emit_sell_event
  $src2 = [regex]::Replace(
    $src,
    '(?s)(def\s+emit_sell_event[\s\S]*?)(\n\s*w\.writerow\(\s*row\s*\))',
    ('$1' + $inject + '$2'),
    1
  )

  if ($src2 -eq $src) { throw 'Could not insert time_et assignment before writerow(row).' }
  $src = $src2
  Write-Host 'Patched emit_sell_event -> added row["time_et"] assignment'
} else {
  Write-Host 'emit_sell_event already sets row["time_et"]'
}

Set-Content -LiteralPath $Path -Value $src -Encoding UTF8
Write-Host "Done -> $Path"
