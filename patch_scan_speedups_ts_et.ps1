param(
  [string]$Path = "C:\TradeAlerts\services\scan_speedups.py"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (!(Test-Path -LiteralPath $Path)) { throw "File not found: $Path" }

$src = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$bak = "$Path.bak_patch_ts_et_$stamp"
Set-Content -LiteralPath $bak -Value $src -Encoding UTF8
Write-Host "Backup -> $bak"

# 1) Add "ts_et" to the header/fieldnames list after "time_et" (first match)
if ($src -notmatch '["'']ts_et["'']') {
  $patHdr = '(?s)(["'']time_et["'']\s*,\s*\n)'
  $repHdr = '$1' + '    "ts_et",' + "`n"
  $src2 = [regex]::Replace($src, $patHdr, $repHdr, 1)
  if ($src2 -eq $src) { throw 'Could not find "time_et" in a fieldnames/header list to insert "ts_et".' }
  $src = $src2
  Write-Host 'Patched header list -> added "ts_et" after "time_et"'
} else {
  Write-Host '"ts_et" already appears in file (header may already be present).'
}

# 2) Ensure row["ts_et"] is set right before writerow(row) (inside log_candidate)
# Only inject once.
if ($src -notmatch 'row\[\s*["'']ts_et["'']\s*\]') {
  $inject = "`n            # Ensure ISO-ish ts_et for Trade Review matching`n" +
            '            row["ts_et"] = row.get("ts_et") or ((row.get("time_et") or "").replace(" ", "T"))' + "`n"

  $src2 = [regex]::Replace(
    $src,
    '(?s)(def\s+log_candidate\s*\([\s\S]*?\):[\s\S]*?)(\n\s*w\.writerow\(\s*row\s*\))',
    ('$1' + $inject + '$2'),
    1
  )

  if ($src2 -eq $src) { throw 'Could not locate log_candidate() writerow(row) to inject ts_et.' }
  $src = $src2
  Write-Host 'Patched log_candidate -> added row["ts_et"] assignment'
} else {
  Write-Host 'log_candidate already sets row["ts_et"]'
}

Set-Content -LiteralPath $Path -Value $src -Encoding UTF8
Write-Host "Done -> $Path"
